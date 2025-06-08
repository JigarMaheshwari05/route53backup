import boto3
import json
import time
from datetime import datetime
import os

def lambda_handler(event, context):
    """
    Lambda function to backup Route 53 hosted zones to S3 bucket.
    Creates JSON backup files for each hosted zone.
    """
    # Initialize clients
    route53 = boto3.client('route53')
    s3 = boto3.client('s3')
    
    # S3 bucket name from environment variable
    s3_bucket = os.environ['S3_BUCKET']
    
    # Get current date/time for folder structure
    now = datetime.now()
    year = now.strftime('%Y')
    month = now.strftime('%m')
    day = now.strftime('%d')
    
    # List all hosted zones
    hosted_zones = route53.list_hosted_zones()
    
    for zone in hosted_zones['HostedZones']:
        zone_id = zone['Id'].split('/')[-1]  # Extract zone ID
        zone_name = zone['Name'].rstrip('.')  # Remove trailing dot
        
        print(f"Processing zone: {zone_name} (ID: {zone_id})")
        
        # Create folder structure for this zone including zone ID to avoid conflicts
        folder_prefix = f"{zone_name}_{zone_id}/{year}/{month}/{day}/"
        
        # Get all records for this zone
        records = []
        paginator = route53.get_paginator('list_resource_record_sets')
        page_iterator = paginator.paginate(HostedZoneId=zone_id)
        
        for page in page_iterator:
            records.extend(page['ResourceRecordSets'])
        
        # Create JSON backup
        json_data = {
            'HostedZoneId': zone_id,
            'HostedZoneName': zone_name,
            'ResourceRecordSets': records
        }
        
        # Create timestamp for filenames
        timestamp = now.strftime('%Y%m%d_%H%M%S')
        
        # Create JSON backup with hosted zone name, zone ID and timestamp
        json_key = folder_prefix + f"{zone_name}_{zone_id}_backup_{timestamp}.json"
        s3.put_object(
            Bucket=s3_bucket,
            Key=json_key,
            Body=json.dumps(json_data, indent=2),
            ContentType='application/json'
        )
        
        print(f"Backup completed for zone {zone_name}")
    
    return {
        'statusCode': 200,
        'body': f'Successfully backed up {len(hosted_zones["HostedZones"])} hosted zones to S3'
    }

# For local testing
if __name__ == "__main__":
    lambda_handler(None, None)
