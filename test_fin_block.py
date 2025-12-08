import os
import django
import sys
from unittest.mock import MagicMock, patch

sys.path.append(r'c:\Users\riaan\source\repos\Vossie')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.test import RequestFactory
from django.contrib.sessions.middleware import SessionMiddleware
from academics.views import transcript
from students.models import Student
from accounts.models import User

def test_financial_block():
    print("Testing Financial Block Logic...")
    
    # 1. Setup Request
    factory = RequestFactory()
    request = factory.get('/academics/transcript/')
    
    # Add session
    middleware = SessionMiddleware(lambda x: None)
    middleware.process_request(request)
    request.session.save()
    
    # Mock User
    user = User.objects.first()
    request.user = user
    
    # Mock Student
    student = Student.objects.first()
    if not student:
        print("SKIP: No student found to test.")
        return

    request.session['active_student_id'] = student.id

    # 2. Mock 'fabric_contact_by_id' to return BLOCKED contact
    with patch('academics.views.fabric_contact_by_id') as mock_fabric:
        mock_fabric.return_value = {
            'contactid': student.external_student_id,
            'btfo_financeblock': True,  # SIMULATE BLOCK
            'firstname': student.first_name
        }
        
        # We also need to mock parent_can_view_student to True
        with patch('academics.views.parent_can_view_student', return_value=True):
            print("  --> Simulating BLOCKED student...")
            response = transcript(request)
            
            content = response.content.decode()
            if "financial block" in content and "Access Restricted" in content:
                print("PASS: Blocked message displayed.")
            else:
                print("FAIL: Blocked message NOT displayed.")
                # print(content[:500]) # Debug

    # 3. Mock 'fabric_contact_by_id' to return UNBLOCKED contact
    with patch('academics.views.fabric_contact_by_id') as mock_fabric:
        mock_fabric.return_value = {
            'contactid': student.external_student_id,
            'btfo_financeblock': False,  # SIMULATE UNBLOCKED
            'firstname': student.first_name
        }
        
        # Iterate over other fetches if needed, or just see if we get past the block check
        # We might hit errors later in the view because we aren't mocking fetchxml, 
        # but if we get past the block check, we won't see "Access Restricted".
        
        with patch('academics.views.parent_can_view_student', return_value=True):
            # We also need to mock fetchxml to avoid network errors or xml parsing errors
            with patch('academics.views.fetchxml', return_value={"value": []}): 
                print("  --> Simulating UNBLOCKED student...")
                response = transcript(request)
                content = response.content.decode()
                
                if "Access Restricted" not in content:
                    print("PASS: Blocked message NOT displayed (as expected).")
                else:
                    print("FAIL: Blocked message displayed for unblocked student.")

test_financial_block()
