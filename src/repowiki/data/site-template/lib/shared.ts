// 저장소 이름과 원격 주소는 repowiki가 사이트를 세울 때 채운다. 템플릿에 특정 저장소를
// 박아 두면 다른 저장소의 사이트가 남의 이름과 남의 주소를 달고 나온다.
export const appName = '__REPOWIKI_APP_NAME__';
export const docsRoute = '/docs';
export const docsImageRoute = '/og/docs';
export const docsContentRoute = '/llms.mdx/docs';

// 분석한 저장소의 원격 주소. 원격이 없으면 빈 문자열이고, 그때는 저장소로 가는 고리를
// 아예 내지 않는다. 없는 주소를 거는 것보다 안 거는 것이 낫다.
export const repoUrl = '__REPOWIKI_REPO_URL__';
