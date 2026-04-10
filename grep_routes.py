with open('app.py', 'r', encoding='utf-8') as f:
  for l in f:
    if '@app.route' in l:
      print(l.strip())