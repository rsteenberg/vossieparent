import os
import django
import sys

sys.path.append(r'c:\Users\riaan\source\repos\Vossie')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from crm.models import Contact

c = Contact.objects.first()
if c:
    print("BT KEYS in raw_data:")
    keys = sorted(c.raw_data.keys())
    for k in keys:
        if k.startswith("bt_") or "block" in k:
            print(f"{k}: {c.raw_data[k]}")
else:
    print("No contacts found.")
