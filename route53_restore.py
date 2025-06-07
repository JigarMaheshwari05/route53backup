#!/usr/bin/env python3
import boto3
import json
import argparse
import sys
from botocore.exceptions import ClientError

def load_backup_file(backup_file_path):
    """Load and validate the JSON backup file."""
    try:
        with open(backup_file_path, 'r') as f:
            backup_data = json.load(f)
        
        # Validate required fields
        required_fields = ['HostedZoneId', 'HostedZoneName', 'ResourceRecordSets']
        for field in required_fields:
            if field not in backup_data:
                print(f"Error: Backup file missing required field: {field}")
                sys.exit(1)
        
        return backup_data
    except FileNotFoundError:
        print(f"Error: Backup file not found: {backup_file_path}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in backup file: {e}")
        sys.exit(1)

def filter_records(records, zone_name):
    """Filter out records that shouldn't be imported."""
    zone_apex = zone_name + '.'
    filtered_records = []
    
    for record in records:
        # Skip SOA and NS records at the zone apex
        if (record['Type'] in ['SOA', 'NS'] and 
            record['Name'] == zone_apex):
            continue
        filtered_records.append(record)
    
    return filtered_records

def verify_hosted_zone(route53_client, zone_id):
    """Verify that the hosted zone exists and get its details."""
    try:
        response = route53_client.get_hosted_zone(Id=zone_id)
        zone_name = response['HostedZone']['Name'].rstrip('.')
        return zone_name
    except ClientError as e:
        if e.response['Error']['Code'] == 'NoSuchHostedZone':
            print(f"Error: Hosted zone {zone_id} not found")
        else:
            print(f"Error verifying hosted zone: {e}")
        sys.exit(1)

def import_records(route53_client, zone_id, records, dry_run=False):
    """Import records into the hosted zone in batches."""
    if not records:
        print("No records to import")
        return
    
    print(f"{'[DRY RUN] ' if dry_run else ''}Importing {len(records)} records...")
    
    # Process records in batches (Route 53 limit is 1000 changes per request)
    batch_size = 100
    total_batches = (len(records) + batch_size - 1) // batch_size
    
    for i in range(0, len(records), batch_size):
        batch = records[i:i + batch_size]
        batch_number = i // batch_size + 1
        
        changes = []
        for record in batch:
            changes.append({
                'Action': 'CREATE',
                'ResourceRecordSet': record
            })
        
        if dry_run:
            print(f"[DRY RUN] Batch {batch_number}/{total_batches}: Would import {len(changes)} records")
            for change in changes:
                record = change['ResourceRecordSet']
                print(f"  - {record['Name']} {record['Type']}")
        else:
            try:
                response = route53_client.change_resource_record_sets(
                    HostedZoneId=zone_id,
                    ChangeBatch={'Changes': changes}
                )
                change_id = response['ChangeInfo']['Id']
                print(f"Batch {batch_number}/{total_batches}: Imported {len(changes)} records (Change ID: {change_id})")
            except ClientError as e:
                print(f"Error importing batch {batch_number}: {e}")
                if 'already exists' in str(e):
                    print("Some records may already exist in the target zone")
                continue

def main():
    parser = argparse.ArgumentParser(
        description='Route 53 Record Import Tool - Import records from JSON backup file',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Import to original hosted zone (from JSON file)
  python route53_restore.py backup.json

  # Import to specific hosted zone
  python route53_restore.py backup.json --zone-id Z1234567890ABC

  # Dry run to see what would be imported
  python route53_restore.py backup.json --dry-run

  # Import to specific zone with dry run
  python route53_restore.py backup.json --zone-id Z1234567890ABC --dry-run
        """
    )
    
    parser.add_argument('backup_file', help='Path to JSON backup file')
    parser.add_argument('--zone-id', help='Target hosted zone ID (if not provided, uses zone ID from backup file)')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be imported without making changes')
    
    args = parser.parse_args()
    
    # Initialize Route 53 client
    try:
        route53 = boto3.client('route53')
    except Exception as e:
        print(f"Error initializing AWS client: {e}")
        print("Make sure your AWS credentials are configured properly")
        sys.exit(1)
    
    # Load backup file
    print(f"Loading backup file: {args.backup_file}")
    backup_data = load_backup_file(args.backup_file)
    
    # Display backup information
    print(f"Backup contains:")
    print(f"  - Zone Name: {backup_data['HostedZoneName']}")
    print(f"  - Original Zone ID: {backup_data['HostedZoneId']}")
    print(f"  - Total Records: {len(backup_data['ResourceRecordSets'])}")
    
    # Determine target hosted zone ID
    if args.zone_id:
        target_zone_id = args.zone_id
        print(f"Target Zone ID: {target_zone_id} (user specified)")
        
        # Verify the target zone exists
        target_zone_name = verify_hosted_zone(route53, target_zone_id)
        print(f"Target Zone Name: {target_zone_name}")
        
        # Warn if zone names don't match
        if target_zone_name != backup_data['HostedZoneName']:
            print(f"WARNING: Target zone name ({target_zone_name}) differs from backup zone name ({backup_data['HostedZoneName']})")
            response = input("Continue anyway? (y/N): ")
            if response.lower() != 'y':
                print("Import cancelled")
                sys.exit(0)
    else:
        target_zone_id = backup_data['HostedZoneId']
        print(f"Target Zone ID: {target_zone_id} (from backup file)")
        
        # Verify the original zone still exists
        verify_hosted_zone(route53, target_zone_id)
    
    # Filter records (remove SOA and NS at zone apex)
    records_to_import = filter_records(backup_data['ResourceRecordSets'], backup_data['HostedZoneName'])
    skipped_count = len(backup_data['ResourceRecordSets']) - len(records_to_import)
    
    if skipped_count > 0:
        print(f"Skipping {skipped_count} records (SOA/NS at zone apex)")
    
    print(f"Records to import: {len(records_to_import)}")
    
    if not records_to_import:
        print("No records to import")
        sys.exit(0)
    
    # Confirm before proceeding (unless dry run)
    if not args.dry_run:
        print(f"\nThis will import {len(records_to_import)} records into hosted zone {target_zone_id}")
        response = input("Continue? (y/N): ")
        if response.lower() != 'y':
            print("Import cancelled")
            sys.exit(0)
    
    # Import records
    import_records(route53, target_zone_id, records_to_import, args.dry_run)
    
    if args.dry_run:
        print("\n[DRY RUN] No changes were made")
    else:
        print(f"\nImport completed successfully!")
        print(f"Imported {len(records_to_import)} records into zone {target_zone_id}")

if __name__ == '__main__':
    main()
