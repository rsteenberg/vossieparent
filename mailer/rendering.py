from django.template.loader import render_to_string

def render_email(template, context):
    subject = template.subject_template.format(**context.get("subject_vars", {}))
    html_body = render_to_string(template.html_template_path, context)
    text_body = render_to_string(template.text_template_path, context) if template.text_template_path else None
    return subject, text_body, html_body
