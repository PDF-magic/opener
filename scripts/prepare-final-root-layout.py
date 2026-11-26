import base64, os, posixpath, re, subprocess
from pathlib import Path
os.chdir(Path(__file__).resolve().parents[1])
moves = {
 "allow-and-open.sh": "src/scan/allow-and-open.sh",
 "install-allow-and-open.sh": "scripts/installation/install-allow-and-open.sh",
 "update-malware-signatures.sh": "src/scanner/update-malware-signatures.sh",
 "Repair Installation.command": "scripts/installation/repair-installation.command",
 "requirements-enhanced-pdf.txt": "requirements/requirements-enhanced-pdf.txt",
}
changed = {}
for filename in filter(None, subprocess.check_output(["git","ls-files","-z"]).decode().split("\0")):
 p = Path(filename)
 if filename in ("scripts/prepare-final-root-layout.py", ".github/workflows/validate-final-root-layout.yml"):
  continue
 if p.suffix not in (".py",".sh",".command",".md",".yml",".yaml",".swift",".json",".js",".mjs",".txt"):
  continue
 try:
  old = p.read_bytes().decode()
 except UnicodeDecodeError:
  continue
 new = old
 for name,dest in moves.items():
  esc = re.escape(name)
  new = re.sub(r'((?:\bROOT|\broot|\brepo_root|\brepository|\brepo|\bREPO|\bPROJECT_ROOT|\bsource_root|\bcheckout|Path\(__file__\)\.resolve\(\)\.parents\[\d+\])\s*/\s*["\x27])'+esc, lambda m:m[1]+dest,new)
  if p.suffix in (".yml",".yaml"):
   new = re.sub(r'(?m)^(\s*-\s*["\x27]?)'+esc+r'(["\x27]?\s*)$',lambda m:m[1]+dest+m[2],new)
   new = re.sub(r'(?<![\w./-])'+esc+r'(?=[\s"\x27\x60]|$)',lambda m:dest if name in ("install-allow-and-open.sh","requirements-enhanced-pdf.txt","Repair Installation.command") or re.search(r'\b(?:bash\s+-n|bash\s+|sh\s+|cp\s+)[^\n]*$',new[:m.start()]) else m[0],new)
  if p.suffix==".md":
   new = re.sub(r'(?<![\w/-])(?:\.\./)+'+esc,posixpath.relpath(dest,p.parent.as_posix()),new)
   if name in ("install-allow-and-open.sh","Repair Installation.command","requirements-enhanced-pdf.txt"):
    new = re.sub(r'(?<![\w/.-])'+esc,dest,new)
  if name=="requirements-enhanced-pdf.txt" and p.suffix not in (".md",".yml",".yaml"):
   new = re.sub(r'(?<![\w/.-])'+esc,dest,new)
 if filename=="install-allow-and-open.sh" or filename.startswith("tests/"):
  for name in ("allow-and-open.sh","update-malware-signatures.sh"):
   new=new.replace("$script_dir/"+name,"$script_dir/"+moves[name])
 if filename=="install-allow-and-open.sh":
  new=new.replace('script_dir="$(cd "$(dirname "$0")" && pwd)"','script_dir="$(cd "$(dirname "$0")/../.." && pwd -P)"')
 if filename=="allow-and-open.sh":
  new=re.sub(r'if \[ -f "\$script_dir/\.gitattributes" \]; then\n.*?\nfi\n','',new,flags=re.S)
 if filename=="Repair Installation.command":
  new=new.replace("$script_dir/scripts/report-install-prerequisites.py","$script_dir/../report-install-prerequisites.py").replace("$script_dir/scripts/confirm-clamav-install.py","$script_dir/../confirm-clamav-install.py")
 if filename=="tests/general/repair-installation.py":
  new=new.replace('self.repair = self.root / REPAIR.name','installation = self.root / "scripts/installation"\n        installation.mkdir(parents=True)\n        self.repair = installation / REPAIR.name').replace('scripts.mkdir()','scripts.mkdir(exist_ok=True)').replace('self.installer = self.root / INSTALLER.name','self.installer = installation / INSTALLER.name').replace('"Repair Installation.command"','"repair-installation.command"')
 if filename=="tests/general/python-source-layout.py":
  new=new.replace('def test_no_root_python_sources(self):','def test_no_root_source_or_runtime_files(self):').replace('name.suffix == ".py"','name.suffix in (".py", ".swift", ".sh", ".command", ".txt")')
 if filename=="scripts/ci-test-scope.py":
  new=new.replace('"requirements/requirements-enhanced-pdf.txt"','"requirements-enhanced-pdf.txt"')
 if new!=old:
  changed[filename]=new
  p.write_bytes(new.encode())
for name,dest in moves.items():
 p=Path(dest)
 assert not p.exists()
 p.parent.mkdir(parents=True,exist_ok=True)
 Path(name).rename(p)
 print("MOVE "+name+" "+dest)
for filename,new in sorted(changed.items()):
 data=new.encode()
 print("CANDIDATE_BEGIN "+filename)
 print("CANDIDATE_SIZE "+str(len(data)))
 encoded=base64.b64encode(data).decode()
 for start in range(0,len(encoded),1200):
  print("CANDIDATE_DATA "+encoded[start:start+1200])
 print("CANDIDATE_END")
print("CANDIDATE_COMPLETE")
subprocess.run(["git","add","-A"],check=True)
