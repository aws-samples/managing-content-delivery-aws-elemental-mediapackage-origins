## Managing content delivery across multiple AWS Elemental MediaPackage origins
Sample code to help configure multiple AWS Elemental MediaPackage VOD origins in a single CloudFront distribution but inspecting a single asset in each MediaPackage group and inferring the unique path pattern to be defined as CloudFront Cache Behavior

## Build

* Clone this repository
* Set 'bucket' and 'region' values to point to your S3 bucket which will hold the code artifacts in the specified AWS REGION
* Install 'Make' (if not done already)
* Run 'make setup' from command line inside the project folder

## Security

See [CONTRIBUTING](CONTRIBUTING.md#security-issue-notifications) for more information.

## License

This library is licensed under the MIT-0 License. See the LICENSE file.
