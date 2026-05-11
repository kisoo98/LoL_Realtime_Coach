import re

def clean_requirements(input_file, output_file):
    with open(input_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    # Packages that are likely to fail on Linux/WSL or are conda-internal
    # audioop-lts requires Python 3.13+, but user is on 3.11 where audioop is built-in.
    skip_packages = {
        'anaconda-anon-usage', 'anaconda-auth', 'anaconda-cli-base', 'conda',
        'conda-anaconda-telemetry', 'conda-anaconda-tos', 'conda-content-trust',
        'conda-libmamba-solver', 'conda-package-handling', 'conda_package_streaming',
        'libmambapy', 'menuinst', 'pypiwin32', 'pywin32', 'pywin32-ctypes',
        'win10toast', 'win32_setctime', 'comtypes', 'dxcam', 'audioop-lts'
    }

    fixed_lines = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith('#'):
            fixed_lines.append(line)
            continue
        
        # Extract package name (everything before == or @ or > or <)
        package_name = re.split(r'==|@|>=|<=|>|<', line)[0].strip()
        
        if package_name.lower() in [p.lower() for p in skip_packages]:
            fixed_lines.append(f'# {line}  # Skipped (Windows-specific or incompatible)')
            continue

        # Remove '@ file://...' part if present
        if ' @ file://' in line:
            fixed_lines.append(package_name)
        else:
            fixed_lines.append(line)

    with open(output_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(fixed_lines) + '\n')

if __name__ == "__main__":
    clean_requirements('requirements.txt', 'requirements_fixed.txt')
