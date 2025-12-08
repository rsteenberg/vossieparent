import os
import django
import sys

# Setup Django environment
sys.path.append(r'c:\Users\riaan\source\repos\Vossie')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from students.fabric import fetch_contact_by_id, fetch_contacts_by_sponsor_email
from crm.service import get_contacts_by_sponsor1_email, get_contact_by_id, is_user_sponsor1_email
from crm.models import Contact

def run_verification():
    print("Starting Lookup Verification...")
    
    # Ensure we have at least one contact
    c = Contact.objects.first()
    if not c:
        print("FAIL: No contacts found in local DB. Run sync_contacts first.")
        return

    print(f"Testing with Contact ID: {c.contact_id} ({c.first_name} {c.last_name})")
    
    # Test 1: Fabric fetch by ID
    # This should hit the local DB and return raw_data
    try:
        res1 = fetch_contact_by_id(c.contact_id)
        if res1 and res1.get('contactid') == c.contact_id:
            print("PASS: Fabric fetch by ID returned correct contact")
        else:
            print(f"FAIL: Fabric fetch by ID returned {res1}")
    except Exception as e:
        print(f"FAIL: Fabric fetch by ID raised exception: {e}")

    # Test 2: Fabric fetch by Sponsor Email (if available)
    sponsor_email = c.sponsor1_email or c.sponsor2_email or c.email
    if sponsor_email:
        print(f"Testing Sponsor Lookup with email: {sponsor_email}")
        try:
            res2 = fetch_contacts_by_sponsor_email(sponsor_email)
            if any(r.get('contactid') == c.contact_id for r in res2):
                 print("PASS: Fabric fetch by Sponsor Email found the contact")
            else:
                 print("FAIL: Fabric fetch by Sponsor Email did NOT find the contact")
        except Exception as e:
            print(f"FAIL: Fabric fetch by Sponsor Email raised exception: {e}")
    else:
        print("SKIP: Contact has no email/sponsor email to test")

    # Test 3: CRM Service fetch by ID
    try:
        res3 = get_contact_by_id(c.contact_id)
        if res3 and res3.get('contactid') == c.contact_id:
            print("PASS: CRM Service fetch by ID returned correct contact")
        else:
             print(f"FAIL: CRM Service fetch by ID returned {res3}")
    except Exception as e:
        print(f"FAIL: CRM Service fetch by ID raised exception: {e}")

    # Test 4: CRM Service fetch by Sponsor Email
    if c.sponsor1_email:
        print(f"Testing CRM Service Sponsor Lookup with email: {c.sponsor1_email}")
        try:
            res4 = get_contacts_by_sponsor1_email(c.sponsor1_email)
            if any(r.get('contactid') == c.contact_id for r in res4):
                 print("PASS: CRM Service fetch by Sponsor Email found the contact")
            else:
                 print("FAIL: CRM Service fetch by Sponsor Email did NOT find the contact")
        except Exception as e:
            print(f"FAIL: CRM Service fetch by Sponsor Email raised exception: {e}")

run_verification()
