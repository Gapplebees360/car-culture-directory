import assert from 'node:assert/strict';
import {authenticateWebsiteWorker,WORKER_AUDIENCE,WORKER_ISSUER} from '../supabase/functions/community/website-worker-auth.mjs';
const {generateKeyPair,SignJWT,jwtVerify}=await import(process.env.UAM_JOSE_TEST_MODULE||'jose');
const {publicKey,privateKey}=await generateKeyPair('RS256');
const base={repository:'Gapplebees360/car-culture-directory',repository_id:'1415129682',ref:'refs/heads/main',workflow_ref:'Gapplebees360/car-culture-directory/.github/workflows/website-inspection.yml@refs/heads/main',event_name:'schedule'};
const sign=async(changes={},options={})=>new SignJWT({...base,...changes}).setProtectedHeader({alg:'RS256'}).setIssuer(options.issuer||WORKER_ISSUER).setAudience(options.audience||WORKER_AUDIENCE)
  .setSubject(options.sub||'repo:Gapplebees360/car-culture-directory:ref:refs/heads/main').setIssuedAt().setExpirationTime(options.expired?Math.floor(Date.now()/1000)-60:'5m').sign(options.key||privateKey);
const verify=(token,options)=>jwtVerify(token,publicKey,options);
assert.equal(await authenticateWebsiteWorker(await sign(),verify),true);
for(const changes of [{repository:'other/repo'},{repository_id:'1'},{ref:'refs/heads/attacker'},{workflow_ref:base.workflow_ref.replace('website-inspection.yml','other.yml')},{event_name:'pull_request'}])assert.equal(await authenticateWebsiteWorker(await sign(changes),verify),false);
assert.equal(await authenticateWebsiteWorker(await sign({}, {audience:'another-service'}),verify),false);
assert.equal(await authenticateWebsiteWorker(await sign({}, {issuer:'https://attacker.invalid'}),verify),false);
assert.equal(await authenticateWebsiteWorker(await sign({}, {sub:'repo:other/repo:ref:refs/heads/main'}),verify),false);
const other=await generateKeyPair('RS256');assert.equal(await authenticateWebsiteWorker(await sign({}, {key:other.privateKey}),verify),false);
assert.equal(await authenticateWebsiteWorker('unsigned.fake.token',verify),false);
assert.equal(await authenticateWebsiteWorker(await sign({}, {expired:true}),verify),false);
console.log('Website worker auth checks passed: signature, issuer, audience, repository identity, branch, workflow and trigger restrictions.');
