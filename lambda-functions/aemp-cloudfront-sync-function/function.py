import json
import boto3
from urllib.parse import urlparse
cloudfront = boto3.client('cloudfront')
aemp_vod = boto3.client('mediapackage-vod')

def handler(event, context):
    print("Event :{}".format(event))
    response = cloudfront.get_distribution_config(Id=event["DistributionId"])
    eTag = response["ETag"]
    distributionConfig = response["DistributionConfig"]
    print("DistributionConfig :{}".format(distributionConfig))
    origins = distributionConfig["Origins"]
    print("ETag :{}".format(eTag))
    print("Origins {}".format(origins))

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
        print("Cache Behaviors exist")
    except:
        print("No Cache Behaviors exist..adding")
        distributionConfig["CacheBehaviors"] = {}
        distributionConfig["CacheBehaviors"]["Items"] = []

    # checking if Origins  exists
    try:
        distributionConfig["Origins"]["Items"]
        print("Some Origins exist")
    except:
        print("No Origins exist..adding")
        distributionConfig["Origins"] = {}
        distributionConfig["Origins"]["Items"] = []

    # check if Origin Shield is enabled, default to False
    originShieldEnabled = False
    try:
        if originShieldRegion and originShieldRegion.strip():
            originShieldEnabled = True
    except:
        print("Origin Shield is not enabled")

    origins = {}
    print("Length of CacheBehavior before :{}".format(len(distributionConfig["CacheBehaviors"]["Items"])))
    print("Length of Origins before :{}".format(len(distributionConfig["Origins"]["Items"])))

    for origin in distributionConfig["Origins"]["Items"]:
        print("Origin = {}".format(origin))
        origins[origin["DomainName"]] = origin["Id"]

    cacheBehaviors = []

    for cb in distributionConfig["CacheBehaviors"]["Items"]:
        cacheBehaviors.append(cb["PathPattern"])

    cacheBehaviors = set(cacheBehaviors)

    for path in pathPatterns.keys():
        if path in cacheBehaviors:
            print("Cache Behavior already defined :{}".format(path))
        else:
            print("Adding new CacheBehavior :{}:{}".format(path,pathPatterns[path]))
            originDetails = pathPatterns[path]
            originDomain = originDetails["OriginDomain"]
            # check to create if MediaPackage origin is defined, if not create a new origin
            if originDomain in origins.keys():
                print("Origin already defined :{}".format(originDomain))
                originId = origins[originDomain]
            else:
                originId = 'EMP-{}'.format(originDomain.split(".")[0])

            newCacheBehavior = create_cache_behavior(path,originId,originDetails["isMSS"])
            distributionConfig["CacheBehaviors"]["Items"].insert(0,newCacheBehavior)
            # check to create if MediaPackage origin is defined, if not create a new origin
            if originDomain in origins.keys():
                print("Origin already defined :{}".format(originDomain))
            else:
                print("Creating new origin for: {}".format(originDomain))
                newOrigin = create_new_origin(originDomain,originId,originShieldEnabled,originShieldRegion)
                distributionConfig["Origins"]["Items"].append(newOrigin)
                origins[originDomain] = originId

    distributionConfig["CacheBehaviors"]["Quantity"] = len(distributionConfig["CacheBehaviors"]["Items"])
    distributionConfig["Origins"]["Quantity"] = len(distributionConfig["Origins"]["Items"])

    print("Length of CacheBehavior after :{}".format(len(distributionConfig["CacheBehaviors"]["Items"])))
    print("Length of Origins after :{}".format(len(distributionConfig["Origins"]["Items"])))

    # print("Origins :{}".format(origins))
    print("Updated DistributionConfig :{}".format(distributionConfig))

    response = cloudfront.update_distribution(DistributionConfig=distributionConfig,Id=distributionId,IfMatch=eTag)

    # print("Origins :{}".format(origins))
    # print("CacheBehaviors :{}".format(cacheBehaviors))

    # response = cloudfront.update_distribution(DistributionConfig=distributionConfig,Id=distributionId,IfMatch=eTag)
    # print("Updated distributionConfig :{}".format(response))

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

    print("Path Pattern|OriginId|isMSS :{}|{}|{}".format(pathPattern,originId,isMSS))
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
        # print("Response :{}".format(response))
        pathPatterns[(generalise_path(response.path, isMSS))] = {'OriginDomain':response.netloc,'isMSS':isMSS}

    # uniquePathPatterns = set(pathPatterns)
    # print("Unique Origins {}".format(uniqueOrigins))
    print("Unique Path Patterns {}".format(pathPatterns))

    return  pathPatterns

def generalise_path(path,isMSS):
    # print(path)
    parts = path.split("/")
    pattern = "/{}/{}/*/{}/*".format(parts[1],parts[2],parts[4])

    # for Microsoft Smooth Streaming append the index.ism/* to the path pattern
    if isMSS:
        pattern = "{}/{}".format(pattern,"index.ism/*")
    # print(pattern)
    return pattern

def get_playable_endpoints(assetIds):

    endpoints = []

    for assetId in assetIds:
        response = aemp_vod.describe_asset(Id=assetId)
        print("Asset Detail {}".format(response["EgressEndpoints"]))
        for endpoint in response["EgressEndpoints"]:
            endpoints.append(endpoint["Url"])

    print("Endpoints {}".format(endpoints))
    return endpoints

def list_assets(event):

    packagingGroups = event["PackagingGroups"].split(",")
    assetIds = []

    for packagingGroup in packagingGroups:
        response = aemp_vod.list_assets(MaxResults=1,PackagingGroupId=packagingGroup);
        for asset in response["Assets"]:
            # print("Asset Info {}".format(asset))
            assetIds.append(asset["Id"])

    print("Asset Ids {}".format(assetIds))
    return assetIds
