# Route 53 Backup Solution

![AWS](https://img.shields.io/badge/AWS?style=for-the-badge&logo=Amazon-web-services)
![CloudFormation](https://img.shields.io/badge/CloudFormation-%23FF9900.svg?style=flat-square&logo=amazon-aws&logoColor=white)
![Python](https://img.shields.io/badge/python-3670A0?style=for-the-badge&logo=python&logoColor=ffdd54)
![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)

A serverless solution to automatically back up all Amazon Route 53 hosted zones to an S3 bucket. This solution creates both JSON format backups (for programmatic use) and BIND-compatible zone files (for importing into Route 53 or other DNS services).

## 📋 Features

- **Complete Backup**: Automatically backs up all Route 53 hosted zones in your AWS account
- **Organized Storage**: Creates folder structure in S3: `{zone_name}/{year}/{month}/{day}/`
- **Dual Format Backups**:
  - JSON file with complete record details: `{zone_name}_backup_{timestamp}.json`
  - BIND-compatible zone file for import: `{zone_name}_{timestamp}.zone`
- **Comprehensive Record Support**: Handles all Route 53 record types, including special formatting for TXT and MX records
- **Alias Record Handling**: Includes comments for Route 53-specific features like alias records
- **Automated Scheduling**: Configurable backup frequency using EventBridge Scheduler
- **Security Best Practices**: Follows least privilege principle for IAM permissions
- **Cost Optimization**: Configures 7-day log retention to minimize CloudWatch costs

## 🏗️ Architecture

This solution deploys the following AWS resources:

- **Lambda Function**: Performs the backup operation
- **S3 Bucket**: Stores the backup files
- **EventBridge Scheduler**: Triggers the Lambda function on a schedule
- **IAM Roles**: Provides necessary permissions with least privilege
- **CloudWatch Logs**: Captures Lambda execution logs with 7-day retention

## 📦 Prerequisites

- AWS account with permissions to create Lambda functions, IAM roles, and S3 buckets
- AWS CLI configured with appropriate credentials (if deploying manually)

## 🚀 Deployment

### Option 1: CloudFormation Deployment (Recommended)

Deploy the entire solution with a single CloudFormation template:

1. Navigate to AWS CloudFormation in your AWS console
2. Select "Create stack" > "With new resources (standard)"
3. Upload the `route53-backup.yaml` template file
4. Configure the parameters:
   - `S3BucketName`: Name prefix for your backup bucket
   - `LambdaFunctionName`: Name for the Lambda function (default: Route53Backup)
   - `BackupSchedule`: How often to run the backup
     - `rate(1 day)` - Daily backup
     - `rate(12 hours)` - Twice daily backup
     - `rate(7 days)` - Weekly backup
     - `cron(0 0 * * ? *)` - Daily at midnight UTC
     - `cron(0 12 ? * MON-FRI *)` - Weekdays at noon UTC
5. Complete the stack creation process

Using AWS CLI:
```bash
aws cloudformation create-stack \
  --stack-name Route53Backup \
  --template-body file://route53-backup.yaml \
  --capabilities CAPABILITY_NAMED_IAM
```

### Option 2: Manual Deployment

If you prefer to set up components individually:

1. Create an S3 bucket for storing backups
2. Set up an IAM role with the required permissions (see IAM Policy section)
3. Deploy the Lambda function using the provided Python code (`route53backup-lambda.py`)
4. Configure an EventBridge Scheduler to trigger the Lambda function

## 🔒 IAM Permissions

### Lambda Execution Role

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "route53:ListHostedZones",
                "route53:ListResourceRecordSets"
            ],
            "Resource": "*"
        },
        {
            "Effect": "Allow",
            "Action": [
                "s3:PutObject"
            ],
            "Resource": "arn:aws:s3:::your-route53-backup-bucket/*"
        },
        {
            "Effect": "Allow",
            "Action": [
                "logs:CreateLogGroup",
                "logs:CreateLogStream",
                "logs:PutLogEvents"
            ],
            "Resource": "arn:aws:logs:region:account-id:log-group:/aws/lambda/your-lambda-function-name:*"
        }
    ]
}
```

### EventBridge Scheduler Execution Role

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": "lambda:InvokeFunction",
            "Resource": "arn:aws:lambda:region:account-id:function:your-lambda-function-name"
        }
    ]
}
```

## 📊 Usage

### Automatic Backups

Once deployed, the solution will automatically back up your Route 53 hosted zones according to the configured schedule using EventBridge Scheduler.

### Manual Backup Trigger

To manually trigger a backup:

```bash
aws lambda invoke \
    --function-name Route53Backup \
    --region your-region \
    output.txt
```

### Accessing Backups

Backups are stored in your S3 bucket with the following path structure:
```
s3://your-bucket/{zone_name}/{year}/{month}/{day}/{zone_name}_{timestamp}.zone
s3://your-bucket/{zone_name}/{year}/{month}/{day}/{zone_name}_backup_{timestamp}.json
```

## 🔄 Restoring from Backup

To restore a hosted zone from a zone file backup:

1. Create a new hosted zone in Route 53 (if needed)
2. In the Route 53 console, select the hosted zone
3. Click "Import zone file"
4. Paste the contents of the zone file (.zone) from your backup
5. Click "Import"

## 🛠️ Customization

You can customize the solution by:

- Modifying the backup schedule in the CloudFormation template
- Adjusting the Lambda function code to change backup formats or folder structure
- Adding S3 lifecycle rules to manage backup retention

## 📝 Resource Retention

This CloudFormation template is configured with deletion policies to protect your resources:

- **S3 Bucket**: The backup bucket is configured with `DeletionPolicy: Retain` to ensure your backups are not deleted if the CloudFormation stack is removed.
- **Lambda Function**: The Lambda function is configured with `DeletionPolicy: Retain` to preserve the function and its configuration.
- **EventBridge Scheduler**: The scheduler is configured with `DeletionPolicy: Retain` to ensure backups continue to run even if the stack is deleted.

This means that if you delete the CloudFormation stack, these resources will remain in your AWS account. To completely remove them, you'll need to delete them manually after stack deletion.

## ⚠️ Troubleshooting

Common issues:

- **Lambda timeout**: Increase the Lambda timeout if you have many hosted zones
- **Permission errors**: Verify the IAM roles have the correct permissions
- **Missing backups**: Check CloudWatch Logs for the Lambda function execution details

## 💰 Cost Considerations

This solution uses several AWS services that may incur costs:

- **Lambda**: Free tier includes 1M free requests per month and 400,000 GB-seconds of compute time
- **S3**: Costs based on storage used and requests made
- **CloudWatch Logs**: First 5GB of logs ingested is free, then $0.50 per GB
- **EventBridge Scheduler**: $0.00864 per schedule per day

With default settings and moderate usage, this solution should cost only a few dollars per month or may even fit within the AWS Free Tier.

## 🔐 Security Considerations

This solution follows AWS security best practices:

- **Least Privilege**: IAM roles have minimal permissions required
- **Read-Only Operations**: The Lambda function only reads Route 53 data, it cannot modify or delete records
- **Secure Transport**: S3 bucket policy enforces HTTPS connections
- **Log Management**: CloudWatch Logs configured with appropriate retention

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

Copyright (c) 2025 Jigar Maheshwari

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

