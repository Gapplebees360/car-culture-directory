// Signed GitHub job identity, restricted to this repository's main-branch workflows.
// No service-role credential or reusable browser secret is issued to the worker.
export const WORKER_AUDIENCE='https://usautomeets.com/website-inspector';
export const WORKER_ISSUER='https://token.actions.githubusercontent.com';
const REPOSITORY='Gapplebees360/car-culture-directory';
const WORKFLOWS=new Set(['daily-scraper.yml','website-inspection.yml'].map(name=>`${REPOSITORY}/.github/workflows/${name}@refs/heads/main`));
export async function authenticateWebsiteWorker(token,verify) {
  if(typeof token!=='string'||token.length>16000||token.split('.').length!==3)return false;
  try{
    const {payload}=await verify(token,{issuer:WORKER_ISSUER,audience:WORKER_AUDIENCE,algorithms:['RS256'],maxTokenAge:'10m',clockTolerance:5,
      requiredClaims:['exp','iat','sub','repository','repository_id','ref','workflow_ref','event_name']});
    return payload.repository===REPOSITORY&&payload.repository_id==='1415129682'&&payload.ref==='refs/heads/main'
      &&WORKFLOWS.has(payload.workflow_ref)&&['push','schedule','workflow_dispatch'].includes(payload.event_name)
      &&[`repo:${REPOSITORY}:ref:refs/heads/main`,`repo:${REPOSITORY}:environment:github-pages`].includes(payload.sub);
  }catch{return false;}
}
