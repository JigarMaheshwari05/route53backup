import boto3
import json
import time
from datetime import datetime
import os

def lambda_handler(event, context):
    """
    Lambda function to backup Route 53 hosted zones to S3 bucket.
    Creates both JSON and zone file formats for each hosted zone.
    """
    # Initialize clients
    route53 = boto3.client('route53')
    s3 = boto3.client('s3')
    
    # S3 bucket name - replace with your bucket name
    s3_bucket = 'bucketname'
    
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
        
        # Create folder structure for this zone
        folder_prefix = f"{zone_name}/{year}/{month}/{day}/"
        
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
        
        # Create JSON backup with hosted zone name and timestamp
        json_key = folder_prefix + f"{zone_name}_backup_{timestamp}.json"
        s3.put_object(
            Bucket=s3_bucket,
            Key=json_key,
            Body=json.dumps(json_data, indent=2),
            ContentType='application/json'
        )
        
        # Create zone file backup with hosted zone name and timestamp
        zone_file_content = generate_zone_file(zone_name, records)
        zone_file_key = folder_prefix + f"{zone_name}_{timestamp}.zone"
        
        s3.put_object(
            Bucket=s3_bucket,
            Key=zone_file_key,
            Body=zone_file_content,
            ContentType='text/plain'
        )
        
        print(f"Backup completed for zone {zone_name}")
    
    return {
        'statusCode': 200,
        'body': f'Successfully backed up {len(hosted_zones["HostedZones"])} hosted zones to S3'
    }

def generate_zone_file(zone_name, records):
    """
    Generate a BIND-compatible zone file from Route 53 records.
    """
    # Start with SOA and default TTL
    zone_file = f"$ORIGIN {zone_name}.\n"
    zone_file += "$TTL 3600\n\n"
    
    # Process each record
    for record in records:
        record_name = record['Name']
        record_type = record['Type']
        record_ttl = record.get('TTL', 3600)
        
        # Skip SOA and NS records at the zone apex as Route 53 will ignore them on import
        if record_type in ['SOA', 'NS'] and record_name == zone_name + '.':
            continue
        
        # Format the record name (remove zone name if it's at the end)
        if record_name == zone_name + '.':
            formatted_name = '@'
        else:
            formatted_name = record_name.replace(f'.{zone_name}.', '')
        
        # Start building the record line
        record_line = f"{formatted_name} {record_ttl} IN {record_type} "
        
        # Handle different record types
        if 'ResourceRecords' in record:
            if record_type == 'TXT':
                # TXT records need special handling with quotes
                values = [f'"{value["Value"].strip('"')}"' for value in record['ResourceRecords']]
                record_line += ' '.join(values)
            elif record_type == 'MX':
                # MX records have priority and value
                values = []
                for value in record['ResourceRecords']:
                    parts = value['Value'].split()
                    if len(parts) >= 2:
                        priority = parts[0]
                        mx_host = ' '.join(parts[1:])
                        values.append(f"{priority} {mx_host}")
                record_line += ' '.join(values)
            else:
                # Standard records
                values = [value['Value'] for value in record['ResourceRecords']]
                record_line += ' '.join(values)
        elif 'AliasTarget' in record:
            # Handle alias records (not standard in BIND, but we'll include as a comment)
            dns_name = record['AliasTarget']['DNSName']
            record_line += f"; ALIAS {dns_name}"
        
        zone_file += record_line + "\n"
    
    return zone_file

# For local testing
if __name__ == "__main__":
    lambda_handler(None, None)
