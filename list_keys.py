import os
import django
import sys

sys.path.append(r'c:\Users\riaan\source\repos\Vossie')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from crm.models import Contact

c = Contact.objects.first()
if c:
    print("ALL KEYS in raw_data:")
    keys = sorted(c.raw_data.keys())
    for k in keys:
        print(k)
else:
    print("No contacts found.")
