.PHONY: all

bucket = S3 BUCKET
project-name = vod-aemp-distribution
region = AWS REGION CODE
version = v1
stack-name = vod-aemp-distribution-$(version)

package:
	mkdir -p dist
	cd lambda-functions/aemp-cloudfront-sync-function && zip -FS -q -r ../../dist/aemp-cloudfront-sync-function.zip *

copycode:
	aws s3 cp dist/ s3://$(bucket)-$(region)/${project-name}/code/$(version)/ --recursive;

copytemplate:
	mkdir -p dist
	sed -e "s/CODE_BUCKET/${bucket}-${region}/g; s/CODE_VERSION/${version}/g; s/PROJECT_NAME/${project-name}/g;" templates/deploy.yaml > dist/deploy.yaml
	aws s3 cp dist/deploy.yaml s3://$(bucket)-$(region)/$(project-name)/templates/$(version)/

updatestack: copytemplate
	aws cloudformation update-stack --stack-name $(stack-name) --region $(region) --capabilities CAPABILITY_IAM \
		--template-url https://s3.amazonaws.com/$(bucket)-$(region)/$(project-name)/templates/$(version)/deploy.yaml

createstack: copytemplate
	aws cloudformation create-stack --stack-name $(stack-name) --template-body file://dist/deploy.yaml \
		--capabilities CAPABILITY_IAM --region $(region)

prepare: clean package copytemplate copycode
setup: prepare createstack
update: copytemplate copycode package updatestack
clean:
	rm -rf dist/*
