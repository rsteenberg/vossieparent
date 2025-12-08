from django.core.management.base import BaseCommand
from crm.models import Contact
from students.fabric import _pyodbc_conn, _row_to_dict, _candidate_tables
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = "Syncs contacts from Fabric/Dynamics to local Contact table."

    def handle(self, *args, **options):
        self.stdout.write("Starting contact sync...")
        
        conn = _pyodbc_conn()
        if not conn:
            self.stdout.write(self.style.ERROR("Could not connect to Fabric DB."))
            return

        try:
            tables = _candidate_tables()
            if not tables:
                self.stdout.write(self.style.ERROR("No candidate tables configured."))
                return

            # Primary table is usually the first one
            schema, table = tables[0]
            self.stdout.write(f"Syncing from [{schema}].[{table}]...")
            
            cursor = conn.cursor()
            
            # Select all columns
            cursor.execute(f"SELECT * FROM [{schema}].[{table}]")
            
            batch_size = 1000
            count = 0
            
            while True:
                rows = cursor.fetchmany(batch_size)
                if not rows:
                    break
                
                for row in rows:
                    row_dict = _row_to_dict(cursor, row)
                    
                    # Normalize keys to lowercase for field mapping
                    normalized_data = {k.lower(): v for k, v in row_dict.items()}
                    
                    # Clean row_dict for JSON serialization
                    # Convert Decimals and datetimes to strings
                    import decimal
                    import datetime
                    
                    clean_raw_data = {}
                    for k, v in row_dict.items():
                        if isinstance(v, decimal.Decimal):
                            clean_raw_data[k] = str(v)
                        elif isinstance(v, (datetime.date, datetime.datetime)):
                            clean_raw_data[k] = v.isoformat()
                        else:
                            clean_raw_data[k] = v
                    
                    contact_id = normalized_data.get('contactid')
                    if not contact_id:
                        continue
                        
                    defaults = {
                        'first_name': normalized_data.get('firstname'),
                        'last_name': normalized_data.get('lastname'),
                        'email': normalized_data.get('emailaddress1'),
                        'sponsor1_email': normalized_data.get('btfh_sponsor1email'),
                        'sponsor2_email': normalized_data.get('btfh_sponsor2email'),
                        'raw_data': clean_raw_data
                    }
                    
                    Contact.objects.update_or_create(
                        contact_id=contact_id,
                        defaults=defaults
                    )
                    count += 1
                
                self.stdout.write(f"Processed {count} records...", ending='\r')
                
            self.stdout.write(self.style.SUCCESS(f"\nSuccessfully synced {count} contacts."))
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error during sync: {e}"))
            logger.exception("Fabric sync failed")
        finally:
            try:
                conn.close()
            except Exception:
                pass
