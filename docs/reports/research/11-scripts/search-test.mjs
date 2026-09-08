import { create, load, search } from 'zbsearch';
import fs from 'node:fs';
const data = JSON.parse(fs.readFileSync('out/api/search','utf8'));
const db = create({ schema: { _: 'string' } });
load(db, data);
for (const term of ['Kafka', 'order service', '주문', '컴포넌트', 'orderflow']) {
  const r = await search(db, { term, limit: 5 });
  console.log(JSON.stringify(term), 'hits:', r.count, r.hits.slice(0,3).map(h => h.document.url ?? h.id));
}
