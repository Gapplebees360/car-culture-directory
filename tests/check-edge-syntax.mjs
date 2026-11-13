import { stripTypeScriptTypes } from 'node:module';
import { readFile, writeFile, unlink } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { spawnSync } from 'node:child_process';
const source=await readFile(new URL('../supabase/functions/community/index.ts',import.meta.url),'utf8');
const temporary=join(tmpdir(),'uam-community-'+process.pid+'.mjs');
try{
 await writeFile(temporary,stripTypeScriptTypes(source));
 const check=spawnSync(process.execPath,['--check',temporary],{encoding:'utf8'});
 if(check.status!==0)throw new Error(check.stderr);
 console.log('Edge Function TypeScript syntax check passed.');
}finally{await unlink(temporary).catch(()=>{});}
