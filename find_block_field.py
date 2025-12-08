import os
import django
import sys

sys.path.append(r'c:\Users\riaan\source\repos\Vossie')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from crm.models import Contact

c = Contact.objects.first()
if c:
    print("Keys in raw_data containing 'block' or 'financial':")
    for k in c.raw_data.keys():
        if "block" in k.lower() or "fin" in k.lower():
            print(f"{k}: {c.raw_data[k]}")
else:
    print("No contacts found.")
