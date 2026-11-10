// Compatibility entry point. The shared C/browser glyph compiler uses Pillow.
const path=require('node:path');
const {spawnSync}=require('node:child_process');
const root=path.resolve(__dirname,'..');
const result=spawnSync(path.join(root,'.venv/bin/python'),[path.join(root,'scripts/build_font.py')],{cwd:root,stdio:'inherit'});
if(result.error)throw result.error;
process.exit(result.status??1);
