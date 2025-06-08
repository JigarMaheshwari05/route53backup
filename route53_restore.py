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

def validate_health_checks(route53_client, records):
    """Validate that health checks referenced in records exist in the target account."""
    print("Validating health check references...")
    
    missing_health_checks = {}
    records_with_missing_hc = []
    
    for record in records:
        if 'HealthCheckId' in record:
            health_check_id = record['HealthCheckId']
            record_display = f"{record['Name']} {record['Type']}"
            if 'SetIdentifier' in record:
                record_display += f" (Set: {record['SetIdentifier']})"
            
            try:
                route53_client.get_health_check(HealthCheckId=health_check_id)
                # Health check exists, record is valid
            except ClientError as e:
                if e.response['Error']['Code'] == 'NoSuchHealthCheck':
                    # Health check doesn't exist
                    if health_check_id not in missing_health_checks:
                        missing_health_checks[health_check_id] = []
                    missing_health_checks[health_check_id].append(record_display)
                    records_with_missing_hc.append(record)
                else:
                    # Other error (permissions, etc.)
                    print(f"Warning: Could not validate health check {health_check_id}: {e}")
    
    return missing_health_checks, records_with_missing_hc

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

def get_existing_records(route53_client, zone_id):
    """Get all existing records from the hosted zone."""
    existing_records = {}
    
    try:
        print("Scanning existing records in target zone...")
        paginator = route53_client.get_paginator('list_resource_record_sets')
        page_iterator = paginator.paginate(HostedZoneId=zone_id)
        
        for page in page_iterator:
            for record in page['ResourceRecordSets']:
                # Create a unique key for each record
                # For routing policy records, include SetIdentifier
                if 'SetIdentifier' in record:
                    key = f"{record['Name']}|{record['Type']}|{record['SetIdentifier']}"
                else:
                    key = f"{record['Name']}|{record['Type']}"
                existing_records[key] = record
        
        return existing_records
    except ClientError as e:
        print(f"Error getting existing records: {e}")
        return {}

def compare_records(backup_record, existing_record):
    """Compare backup record with existing record to detect differences."""
    differences = []
    
    # Compare TTL
    backup_ttl = backup_record.get('TTL')
    existing_ttl = existing_record.get('TTL')
    if backup_ttl != existing_ttl:
        differences.append(f"TTL: {existing_ttl} -> {backup_ttl}")
    
    # Compare ResourceRecords
    backup_values = backup_record.get('ResourceRecords', [])
    existing_values = existing_record.get('ResourceRecords', [])
    if backup_values != existing_values:
        backup_vals = [r['Value'] for r in backup_values]
        existing_vals = [r['Value'] for r in existing_values]
        differences.append(f"Values: {existing_vals} -> {backup_vals}")
    
    # Compare AliasTarget
    backup_alias = backup_record.get('AliasTarget')
    existing_alias = existing_record.get('AliasTarget')
    if backup_alias != existing_alias:
        if existing_alias and backup_alias:
            differences.append(f"Alias: {existing_alias.get('DNSName')} -> {backup_alias.get('DNSName')}")
        elif existing_alias:
            differences.append(f"Alias: {existing_alias.get('DNSName')} -> Standard record")
        elif backup_alias:
            differences.append(f"Standard record -> Alias: {backup_alias.get('DNSName')}")
    
    # Compare routing policy fields
    routing_fields = ['Weight', 'Region', 'GeoLocation', 'Failover', 'MultiValueAnswer', 'HealthCheckId']
    for field in routing_fields:
        backup_val = backup_record.get(field)
        existing_val = existing_record.get(field)
        if backup_val != existing_val:
            differences.append(f"{field}: {existing_val} -> {backup_val}")
    
    return differences

def run_preflight_check(route53_client, zone_id, records_to_import):
    """Run preflight check to identify conflicts, health check issues, and categorize records."""
    print("\n" + "="*60)
    print("PREFLIGHT CHECK - Analyzing records...")
    print("="*60)
    
    # First, validate health checks
    missing_health_checks, records_with_missing_hc = validate_health_checks(route53_client, records_to_import)
    
    # Remove records with missing health checks from import list
    valid_records_to_import = [r for r in records_to_import if r not in records_with_missing_hc]
    
    # Get existing records
    existing_records = get_existing_records(route53_client, zone_id)
    print(f"Found {len(existing_records)} existing records in target zone")
    
    # Categorize valid records
    records_to_create = []
    records_to_skip = []
    conflicting_records = []
    
    for record in valid_records_to_import:
        # Create record key
        if 'SetIdentifier' in record:
            key = f"{record['Name']}|{record['Type']}|{record['SetIdentifier']}"
            display_name = f"{record['Name']} {record['Type']} (Set: {record['SetIdentifier']})"
        else:
            key = f"{record['Name']}|{record['Type']}"
            display_name = f"{record['Name']} {record['Type']}"
        
        if key in existing_records:
            existing_record = existing_records[key]
            differences = compare_records(record, existing_record)
            
            if differences:
                # Record exists but has different values - CONFLICT
                conflicting_records.append({
                    'record': record,
                    'existing': existing_record,
                    'differences': differences,
                    'key': key,
                    'display_name': display_name
                })
            else:
                # Record exists and is identical - SKIP
                records_to_skip.append({
                    'record': record,
                    'key': key,
                    'display_name': display_name
                })
        else:
            # Record doesn't exist - CREATE
            records_to_create.append(record)
    
    # Display preflight results
    print(f"\nPREFLIGHT CHECK RESULTS:")
    print(f"✅ {len(records_to_create)} records to CREATE (new records)")
    print(f"⚠️  {len(conflicting_records)} records CONFLICT (exist with different values)")
    print(f"ℹ️  {len(records_to_skip)} records to SKIP (identical records already exist)")
    
    # Show health check issues
    if missing_health_checks:
        print(f"🚫 {len(records_with_missing_hc)} records SKIPPED (missing health checks)")
        print(f"\nMISSING HEALTH CHECKS:")
        for health_check_id, affected_records in missing_health_checks.items():
            print(f"❌ Health Check ID: {health_check_id}")
            print(f"   Please create this health check in the target account first.")
            print(f"   Affected records:")
            for record_name in affected_records:
                print(f"   - {record_name}")
            print()
        
        print(f"💡 RECOMMENDATION:")
        print(f"   1. Create the missing health checks in your target account")
        print(f"   2. Re-run the import after health checks are created")
        print(f"   3. Or remove health check references from the backup file")
    
    # Show conflicting records details
    if conflicting_records:
        print(f"\nCONFLICTING RECORDS:")
        for i, item in enumerate(conflicting_records[:10], 1):  # Show first 10
            print(f"{i}. {item['display_name']}")
            for diff in item['differences']:
                print(f"   {diff}")
        
        if len(conflicting_records) > 10:
            print(f"   ... and {len(conflicting_records) - 10} more conflicting records")
    
    # Show records to skip (first few)
    if records_to_skip:
        print(f"\nRECORDS TO SKIP (identical):")
        for i, item in enumerate(records_to_skip[:5], 1):  # Show first 5
            print(f"{i}. {item['display_name']}")
        
        if len(records_to_skip) > 5:
            print(f"   ... and {len(records_to_skip) - 5} more identical records")
    
    return records_to_create, conflicting_records, records_to_skip

def get_user_choice_for_conflicts(conflicting_records):
    """Get user's choice on how to handle conflicting records."""
    if not conflicting_records:
        return 'skip'  # No conflicts, proceed normally
    
    print(f"\n" + "="*60)
    print("CONFLICT RESOLUTION")
    print("="*60)
    print(f"Found {len(conflicting_records)} conflicting records.")
    print("\nOptions:")
    print("  1. Skip conflicting records (safe - only import new records)")
    print("  2. Overwrite conflicting records (replace existing with backup values)")
    print("  3. Cancel import")
    
    while True:
        choice = input("\nChoose option (1/2/3): ").strip()
        if choice == '1':
            print("✅ Will skip conflicting records and only import new records")
            return 'skip'
        elif choice == '2':
            print("⚠️  Will overwrite existing records with backup values")
            return 'overwrite'
        elif choice == '3':
            print("❌ Import cancelled")
            return 'cancel'
        else:
            print("Please enter 1, 2, or 3")

def import_records(route53_client, zone_id, records, dry_run=False):
    """Import records into the hosted zone with preflight check and conflict handling."""
    if not records:
        print("No records to import")
        return
    
    # Run preflight check
    records_to_create, conflicting_records, records_to_skip = run_preflight_check(
        route53_client, zone_id, records
    )
    
    # Get user choice for handling conflicts
    if not dry_run:
        user_choice = get_user_choice_for_conflicts(conflicting_records)
        if user_choice == 'cancel':
            return
    else:
        user_choice = 'skip'  # For dry run, show skip behavior
    
    # Prepare final list of changes
    changes_to_make = []
    
    # Add CREATE actions for new records
    for record in records_to_create:
        changes_to_make.append({
            'Action': 'CREATE',
            'ResourceRecordSet': record
        })
    
    # Handle conflicting records based on user choice
    if user_choice == 'overwrite':
        for item in conflicting_records:
            changes_to_make.append({
                'Action': 'UPSERT',  # UPSERT creates or updates
                'ResourceRecordSet': item['record']
            })
    
    if not changes_to_make:
        print("\n✅ No changes to make - all records already exist with identical values")
        return
    
    # Show final summary
    print(f"\n" + "="*60)
    print("IMPORT SUMMARY")
    print("="*60)
    create_count = len([c for c in changes_to_make if c['Action'] == 'CREATE'])
    update_count = len([c for c in changes_to_make if c['Action'] == 'UPSERT'])
    
    print(f"Will CREATE: {create_count} new records")
    print(f"Will UPDATE: {update_count} existing records")
    print(f"Will SKIP: {len(records_to_skip)} identical records")
    
    if user_choice == 'skip' and conflicting_records:
        print(f"Will SKIP: {len(conflicting_records)} conflicting records")
    
    print(f"\n{'[DRY RUN] ' if dry_run else ''}Processing {len(changes_to_make)} changes...")
    
    # Process changes in batches
    batch_size = 100
    total_batches = (len(changes_to_make) + batch_size - 1) // batch_size
    
    for i in range(0, len(changes_to_make), batch_size):
        batch = changes_to_make[i:i + batch_size]
        batch_number = i // batch_size + 1
        
        if dry_run:
            print(f"[DRY RUN] Batch {batch_number}/{total_batches}: Would process {len(batch)} changes")
            for change in batch:
                record = change['ResourceRecordSet']
                action = change['Action']
                set_id = f" (Set: {record['SetIdentifier']})" if 'SetIdentifier' in record else ""
                print(f"  - {action}: {record['Name']} {record['Type']}{set_id}")
        else:
            try:
                response = route53_client.change_resource_record_sets(
                    HostedZoneId=zone_id,
                    ChangeBatch={'Changes': batch}
                )
                change_id = response['ChangeInfo']['Id']
                print(f"✅ Batch {batch_number}/{total_batches}: Processed {len(batch)} changes (Change ID: {change_id})")
            except ClientError as e:
                print(f"❌ Error processing batch {batch_number}: {e}")
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
        
        # BLOCK import if zone names don't match (domain apex validation)
        if target_zone_name != backup_data['HostedZoneName']:
            print(f"\n❌ ERROR: Domain mismatch detected!")
            print(f"   Backup domain: {backup_data['HostedZoneName']}")
            print(f"   Target domain: {target_zone_name}")
            print(f"\n🚫 Import BLOCKED: Cannot import records from one domain to another.")
            print(f"   This would create non-functional DNS records.")
            print(f"   Please use the correct hosted zone ID for domain: {backup_data['HostedZoneName']}")
            sys.exit(1)
    else:
        target_zone_id = backup_data['HostedZoneId']
        print(f"Target Zone ID: {target_zone_id} (from backup file)")
        
        # Verify the original zone still exists
        target_zone_name = verify_hosted_zone(route53, target_zone_id)
        print(f"Target Zone Name: {target_zone_name}")
        
        # Double-check domain consistency (should always match, but safety check)
        if target_zone_name != backup_data['HostedZoneName']:
            print(f"\n❌ ERROR: Backup file inconsistency detected!")
            print(f"   Expected domain: {backup_data['HostedZoneName']}")
            print(f"   Actual zone domain: {target_zone_name}")
            print(f"\n🚫 Import BLOCKED: Backup file may be corrupted or zone has been modified.")
            sys.exit(1)
    
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
