import os
import re

endpoints_map = {
    'login': 'auth.login',
    'logout': 'auth.logout',
    'index': 'main.index',
    'dashboard': 'main.dashboard',
    'my_tasks': 'main.my_tasks',
    'download_file': 'main.download_file',
    
    'labs_list': 'labs.labs_list',
    'labs_create': 'labs.labs_create',
    'labs_edit': 'labs.labs_edit',
    'labs_delete': 'labs.labs_delete',
    
    'users_list': 'users.users_list',
    'users_create': 'users.users_create',
    'users_edit': 'users.users_edit',
    'users_delete': 'users.users_delete',
    
    'commitments_list': 'commitments.commitments_list',
    'commitments_create': 'commitments.commitments_create',
    'commitments_edit': 'commitments.commitments_edit',
    'commitments_detail': 'commitments.commitments_detail',
    'commitments_delete': 'commitments.commitments_delete',
    'progress_update': 'commitments.progress_update',
    
    'reports': 'reports.reports',
    'api_stats': 'api.api_stats',
    'api_timeline': 'api.api_timeline',
    'api_lab_users': 'api.api_lab_users'
}

def replace_in_file(fp):
    with open(fp, 'r', encoding='utf-8') as f:
        text = f.read()

    for old_ep, new_ep in endpoints_map.items():
        # Replace occurrences inside url_for('something', ...)
        # Regex carefully looks for url_for('something' or url_for("something"
        text = re.sub(rf"url_for\(['\"]{old_ep}['\"]", f"url_for('{new_ep}'", text)

    with open(fp, 'w', encoding='utf-8') as f:
        f.write(text)

# Patch templates
for root, _, files in os.walk('templates'):
    for file in files:
        if file.endswith('.html'):
            replace_in_file(os.path.join(root, file))

# Patch python files
for root, _, files in os.walk('app'):
    for file in files:
        if file.endswith('.py'):
            replace_in_file(os.path.join(root, file))

print("Patched url_for globally!")
