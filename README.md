# Route 53 Backup & Restore Solution

[![AWS](https://img.shields.io/badge/AWS-%23FF9900.svg?logo=amazon-web-services&logoColor=white)](https://aws.amazon.com/)
[![Python](https://img.shields.io/badge/Python-3776AB?logo=python&logoColor=fff)](https://www.python.org/)
[![CloudFormation](https://img.shields.io/badge/CloudFormation-FF4F8B?logo=amazon-web-services&logoColor=white)](https://aws.amazon.com/cloudformation/)
[![Route 53](https://img.shields.io/badge/Route_53-0052CC?logo=amazon-web-services&logoColor=white)](https://aws.amazon.com/route53/)

A serverless solution to automatically back up and restore Amazon Route 53 hosted zones. This solution creates JSON format backups with comprehensive restore capabilities for disaster recovery and cross-account migrations.

## 📋 Features

### Backup Features
- **Complete Backup**: Automatically backs up all Route 53 hosted zones in your AWS account
- **Organized Storage**: Creates folder structure in S3: `{zone_name}_{zone_id}/{year}/{month}/{day}/`
- **Duplicate Zone Handling**: Supports multiple zones with same domain name (public/private zones)
- **JSON Format**: Complete record details with routing policies and health checks preserved
- **Comprehensive Record Support**: Handles all Route 53 record types, including special formatting for TXT and MX records
- **Alias Record Handling**: Preserves Route 53-specific features like alias records with full metadata
- **Automated Scheduling**: Configurable backup frequency using EventBridge Scheduler

### Restore Features
- **Intelligent Restoration**: Smart conflict detection and resolution
- **Domain Validation**: Prevents accidental cross-domain imports
- **Health Check Validation**: Detects missing health checks and skips affected records
- **Preflight Checks**: Comprehensive validation before making any changes
- **Flexible Targeting**: Restore to original zone or specify different zone ID
- **Dry Run Mode**: Preview changes without making modifications
- **Cross-Account Support**: Safe migration between AWS accounts

## 🏗️ Architecture

This solution deploys the following AWS resources:

- **Lambda Function**: Performs the backup operation
- **S3 Bucket**: Stores the JSON backup files
- **EventBridge Scheduler**: Triggers the Lambda function on a schedule
- **IAM Roles**: Provides necessary permissions with least privilege
- **CloudWatch Logs**: Captures Lambda execution logs with 7-day retention

## 📦 Prerequisites

### For Backup Deployment
- AWS account with permissions to create Lambda functions, IAM roles, and S3 buckets
- AWS CLI configured with appropriate credentials (if deploying manually)

### For Restore Script

#### System Requirements
- **Python 3.7+** (Python 3.8+ recommended)
- **Operating System**: Linux, macOS, or Windows with Python support

#### Python Dependencies
Install required Python packages:
```bash
pip install boto3>=1.26.0
```

#### AWS Configuration
- **AWS CLI configured** with appropriate credentials
- **IAM permissions** for Route 53 and health check operations (see IAM Policy section)

## 🚀 Deployment

### Option 1: CloudFormation Deployment (Recommended)

Deploy the entire solution with a single CloudFormation template:

#### CloudFormation Parameters

| Parameter | Description | Default Value | Possible Values | Example |
|-----------|-------------|---------------|-----------------|---------|
| **S3BucketName** | Name prefix for the S3 backup bucket | `route53-backups` | Any valid S3 bucket name prefix | `my-route53-backups` |
| **LambdaFunctionName** | Name for the Lambda function | `Route53Backup` | Valid Lambda function name | `MyRoute53Backup` |
| **BackupSchedule** | Schedule expression for automated backups | `rate(1 day)` | See schedule options below | `rate(12 hours)` |

#### Backup Schedule Options

**Rate Expressions:**
- `rate(1 minute)` - Every minute (testing only)
- `rate(5 minutes)` - Every 5 minutes
- `rate(1 hour)` - Every hour
- `rate(6 hours)` - Every 6 hours
- `rate(12 hours)` - Twice daily
- `rate(1 day)` - Daily (recommended)
- `rate(7 days)` - Weekly

**Cron Expressions:**
- `cron(0 0 * * ? *)` - Daily at midnight UTC
- `cron(0 12 * * ? *)` - Daily at noon UTC
- `cron(0 0 ? * MON *)` - Weekly on Monday at midnight
- `cron(0 2 ? * MON-FRI *)` - Weekdays at 2 AM UTC
- `cron(0 0 1 * ? *)` - Monthly on the 1st at midnight
- `cron(0 0 ? * SUN *)` - Weekly on Sunday at midnight


**Using AWS Console:**
1. Navigate to AWS CloudFormation in your AWS console
2. Select "Create stack" > "With new resources (standard)"
3. Upload the `route53-backup.yaml` template file
4. Configure the parameters as needed
5. Complete the stack creation process



## 🔐 IAM Policies

### Backup Lambda Function 
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
            "Resource": "arn:aws:s3:::your-backup-bucket/*"
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
            "Action": [
                "lambda:InvokeFunction"
            ],
            "Resource": "arn:aws:lambda:*:*:function:your-lambda-function-name"
        }
    ]
}
```

### Restore Script IAM Policy 
```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "Route53RestorePermissions",
            "Effect": "Allow",
            "Action": [
                "route53:GetHostedZone",
                "route53:ListResourceRecordSets",
                "route53:ChangeResourceRecordSets"
            ],
            "Resource": "*"
        },
        {
            "Sid": "HealthCheckValidation",
            "Effect": "Allow",
            "Action": [
                "route53:GetHealthCheck"
            ],
            "Resource": "*"
        },
        {
            "Sid": "S3BackupAccess",
            "Effect": "Allow",
            "Action": [
                "s3:GetObject"
            ],
            "Resource": "arn:aws:s3:::your-backup-bucket/*"
        }
    ]
}
```

## 📊 Usage

### Automatic Backups
Once deployed, backups run automatically according to the configured schedule.

### Manual Backup Trigger
```bash
aws lambda invoke \
    --function-name Route53Backup \
    --region your-region \
    output.txt
```

### Backup File Structure
```
s3://your-backup-bucket/
├── example.com_Z1234567890ABC/
│   └── 2025/06/08/
│       └── example.com_Z1234567890ABC_backup_20250608_100000.json
└── example.com_Z0987654321XYZ/  # Private zone with same domain
    └── 2025/06/08/
        └── example.com_Z0987654321XYZ_backup_20250608_100000.json
```

## 📖 Restore Process

### Basic Usage

#### Restore to Original Zone
```bash
python route53_restore.py backup.json
```

#### Restore to Different Zone
```bash
python route53_restore.py backup.json --zone-id Z1234567890ABC
```

#### Dry Run (Preview Changes)
```bash
python route53_restore.py backup.json --dry-run
```

### Preflight Checks
The restore script performs comprehensive validation:

1. **Domain Validation**: Ensures backup domain matches target zone
2. **Health Check Validation**: Verifies referenced health checks exist
3. **Conflict Detection**: Identifies existing records with different values
4. **Record Categorization**: Classifies records as CREATE, UPDATE, or SKIP

### Example Preflight Output
```
PREFLIGHT CHECK RESULTS:
✅ 15 records to CREATE (new records)
⚠️  3 records CONFLICT (exist with different values)
ℹ️  5 records to SKIP (identical records already exist)
🚫 2 records SKIPPED (missing health checks)

MISSING HEALTH CHECKS:
❌ Health Check ID: hc-1234567890abcdef
   Please create this health check in the target account first.
   Affected records:
   - api.example.com A (Set: primary)

💡 RECOMMENDATION:
   1. Create the missing health checks in your target account
   2. Re-run the import after health checks are created
```

## ⚠️ Troubleshooting

### Backup Issues
- **Lambda timeout**: Increase timeout if you have many hosted zones
- **Permission errors**: Verify IAM roles have correct permissions
- **Missing backups**: Check CloudWatch Logs for execution details


## 💰 Cost Considerations

- **Lambda**: Free tier includes 1M free requests per month
- **S3**: Costs based on storage used and requests made
- **CloudWatch Logs**: First 5GB of log ingestion is free, storage costs ~$0.03 per GB per month (with 7-day retention, costs are minimal)
- **EventBridge Scheduler**: $1.05/million scheduled invocations per month, after 14 million free invocations per month (Mumbai region ap-south-1)

## 🔐 Security Best Practices

- **Least Privilege**: IAM roles have minimal required permissions
- **Read-Only Backup**: Lambda function only reads Route 53 data
- **Secure Transport**: S3 bucket policy enforces HTTPS connections
- **Domain Validation**: Prevents cross-domain imports
- **Health Check Validation**: Prevents broken record imports

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.
