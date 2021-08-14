import json
import boto3
import logging
from urllib.parse import urlparse
cloudfront = boto3.client('cloudfront')
aemp_vod = boto3.client('mediapackage-vod')

log = logging.getLogger()
log.setLevel(logging.INFO)

def handler(event, context):
    log.info(f'Event :{event}')
    #Sample event object
    # {
    #    "DistributionId": "E2UZBZ6X6T11VU",
    #    "PackagingGroups": "VODWorkflow-packaging-group,me0010-vodjitp8-f7fb0b21d693-vod-package",
    #    "OriginShieldRegion": "eu-west-1"
    # }

    response = cloudfront.get_distribution_config(Id=event["DistributionId"])

    # fetch the ETag which is used later while updating the distribution

    eTag = response["ETag"]
    log.debug(f'ETag :{eTag}')
    distributionConfig = response["DistributionConfig"]
    log.debug(f'DistributionConfig :{distributionConfig}')
    origins = distributionConfig["Origins"]
    log.debug(f'Origins {origins}')

    # Get the Asset Id from each Packaging Group
    assetIds = list_assets(event)

    # Get the playback URLs from those assets
    endpoints = get_playable_endpoints(assetIds)

    # Determine the unique list of origins and path patterns which need to be updated
    pathPatterns = get_origin_pathpatterns(endpoints)

    originShieldRegion = event["OriginShieldRegion"]

    update_distribution_config(pathPatterns,distributionConfig,event["DistributionId"],eTag,originShieldRegion)
    return {
        'statusCode': 200,
        'body': 'Configuration complete.Please wait for the updates on the CloudFront distribution to finish.You can check the status here https://console.aws.amazon.com/cloudfront/home?#distribution-settings:{}'.format(event["DistributionId"])
    }

def update_distribution_config(pathPatterns,distributionConfig, distributionId, eTag, originShieldRegion):

    # checking if Cache Behaviors exists
    try:
        distributionConfig["CacheBehaviors"]["Items"]
        log.debug('Cache Behaviors exist')
    except:
        log.debug('No Cache Behaviors exist..adding')
        distributionConfig["CacheBehaviors"] = {}
        distributionConfig["CacheBehaviors"]["Items"] = []

    # checking if Origins  exists
    try:
        distributionConfig["Origins"]["Items"]
        log.debug('Some Origins exist')
    except:
        log.debug('No Origins exist..preparing to add a new origin')
        distributionConfig["Origins"] = {}
        distributionConfig["Origins"]["Items"] = []

    # check if Origin Shield is enabled, default to False
    originShieldEnabled = False
    try:
        if originShieldRegion and originShieldRegion.strip():
            originShieldEnabled = True
    except:
        log.debug('Origin Shield is not enabled')

    origins = {}
    log.info(f'Length of CacheBehavior before :{len(distributionConfig["CacheBehaviors"]["Items"])}')
    log.info(f'Length of Origins before :{len(distributionConfig["Origins"]["Items"])}')

    for origin in distributionConfig["Origins"]["Items"]:
        log.debug(f"Origin = {origin}")
        origins[origin["DomainName"]] = origin["Id"]

    cacheBehaviors = []

    for cb in distributionConfig["CacheBehaviors"]["Items"]:
        cacheBehaviors.append(cb["PathPattern"])

    cacheBehaviors = set(cacheBehaviors)

    for path in pathPatterns.keys():
        if path in cacheBehaviors:
            log.info(f'Cache Behavior already defined :{path}')
        else:
            log.info(f'Adding new CacheBehavior :{path}:{pathPatterns[path]}')
            originDetails = pathPatterns[path]
            originDomain = originDetails["OriginDomain"]
            # check to create if MediaPackage origin is defined, if not create a new origin
            if originDomain in origins.keys():
                log.info(f'Origin already defined :{originDomain}')
                originId = origins[originDomain]
            else:
                originId = 'EMP-{}'.format(originDomain.split(".")[0])

            newCacheBehavior = create_cache_behavior(path,originId,originDetails["isMSS"])
            distributionConfig["CacheBehaviors"]["Items"].insert(0,newCacheBehavior)
            # check to create if MediaPackage origin is defined, if not create a new origin
            if originDomain in origins.keys():
                log.debug(f'Origin already defined :{originDomain}')
            else:
                log.debug(f'Creating new origin for: {originDomain}')
                newOrigin = create_new_origin(originDomain,originId,originShieldEnabled,originShieldRegion)
                distributionConfig["Origins"]["Items"].append(newOrigin)
                origins[originDomain] = originId

    distributionConfig["CacheBehaviors"]["Quantity"] = len(distributionConfig["CacheBehaviors"]["Items"])
    distributionConfig["Origins"]["Quantity"] = len(distributionConfig["Origins"]["Items"])

    log.info(f'Length of CacheBehavior after :{len(distributionConfig["CacheBehaviors"]["Items"])}')
    log.info(f'Length of Origins after :{len(distributionConfig["Origins"]["Items"])}')

    log.debug(f'Origins :{origins}')
    log.debug(f'Updated DistributionConfig :{distributionConfig}')

    response = cloudfront.update_distribution(DistributionConfig=distributionConfig,Id=distributionId,IfMatch=eTag)
    log.debug(f'Updated distributionConfig :{response}')

def create_new_origin(originDomain,originId,originShieldEnabled,originShieldRegion):

    origin = {'Id': originId, 'DomainName': originDomain, 'OriginPath': '', 'CustomHeaders': {'Quantity': 0},
    'CustomOriginConfig': {'HTTPPort': 80, 'HTTPSPort': 443,
    'OriginProtocolPolicy': 'https-only', 'OriginSslProtocols': {'Quantity': 3, 'Items': ['TLSv1', 'TLSv1.1', 'TLSv1.2']},
    'OriginReadTimeout': 30, 'OriginKeepaliveTimeout': 5}, 'ConnectionAttempts': 3, 'ConnectionTimeout': 10}

    # if origin shield is enabled set this origin shield AWS Region
    if originShieldEnabled:
        origin['OriginShield'] = {'Enabled': originShieldEnabled, 'OriginShieldRegion': originShieldRegion}

    return origin

def create_cache_behavior(pathPattern,originId,isMSS):

    log.debug(f'Path Pattern|OriginId|isMSS :{pathPattern}|{originId}|{isMSS}')
    behavior = {'PathPattern': pathPattern, 'TargetOriginId': originId, 'TrustedSigners': {'Enabled': False, 'Quantity': 0},
    'ViewerProtocolPolicy': 'redirect-to-https', 'AllowedMethods': {'Quantity': 3, 'Items': ['HEAD', 'GET','OPTIONS'],
    'CachedMethods': {'Quantity': 3, 'Items': ['HEAD', 'GET','OPTIONS']}}, 'SmoothStreaming': isMSS, 'Compress': False,
    'LambdaFunctionAssociations': {'Quantity': 0}, 'FieldLevelEncryptionId': '',
    # 'ForwardedValues': {'QueryString': True, 'Cookies': {'Forward': 'none'},
    # 'Headers': {'Quantity': 0}, 'QueryStringCacheKeys': {'Quantity': 3, 'Items': ['end', 'm', 'start']}},
    'CachePolicyId':'08627262-05a9-4f76-9ded-b50ca2e3a84f'}
    return behavior

def get_origin_pathpatterns(endpoints):

    pathPatterns = {}

    for endpoint in endpoints:
        response = urlparse(endpoint)
        isMSS = False
        if ".ism" in response.path:
            isMSS = True
        pathPatterns[(generalise_path(response.path, isMSS))] = {'OriginDomain':response.netloc,'isMSS':isMSS}

    log.debug(f'Unique Path Patterns {pathPatterns}')

    return  pathPatterns

def generalise_path(path,isMSS):
    parts = path.split("/")
    pattern = "/{}/{}/*/{}/*".format(parts[1],parts[2],parts[4])

    # for Microsoft Smooth Streaming append the index.ism/* to the path pattern
    if isMSS:
        pattern = "{}/{}".format(pattern,"index.ism/*")
    return pattern

def get_playable_endpoints(assetIds):

    endpoints = []

    for assetId in assetIds:
        response = aemp_vod.describe_asset(Id=assetId)
        log.debug(f'Asset Detail {response["EgressEndpoints"]}')
        for endpoint in response["EgressEndpoints"]:
            endpoints.append(endpoint["Url"])

    log.debug(f'Endpoints {endpoints}')
    return endpoints

def list_assets(event):

    packagingGroups = event["PackagingGroups"].split(",")
    assetIds = []

    for packagingGroup in packagingGroups:
        response = aemp_vod.list_assets(MaxResults=1,PackagingGroupId=packagingGroup);
        for asset in response["Assets"]:
            assetIds.append(asset["Id"])

    log.debug(f'Asset Ids {assetIds}')
    return assetIds
