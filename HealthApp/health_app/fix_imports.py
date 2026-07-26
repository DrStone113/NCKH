import os
import glob

files = glob.glob('/root/NCKH/NCKH/HealthApp/health_app/lib/features/*/*/*.dart')
for f in files:
    with open(f, 'r') as file:
        content = file.read()
    
    new_content = content.replace("import '../theme/", "import '../../../theme/")
    new_content = new_content.replace("import '../providers/", "import '../../../providers/")
    new_content = new_content.replace("import '../models/", "import '../../../models/")
    new_content = new_content.replace("import '../widgets/", "import '../../../widgets/")
    new_content = new_content.replace("import '../services/", "import '../../../services/")
    
    if new_content != content:
        with open(f, 'w') as file:
            file.write(new_content)
        print(f"Fixed {f}")
