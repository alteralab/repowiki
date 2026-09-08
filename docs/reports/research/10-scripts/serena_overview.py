"""Call Serena's get_symbols_overview over MCP stdio for given files. Usage: serena_overview.py <project> <rel_path>..."""
import asyncio, sys, json, time
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
proj=sys.argv[1]; files=sys.argv[2:]
async def main():
    params=StdioServerParameters(command='/Users/angyojun/.local/bin/serena', args=['start-mcp-server','--transport','stdio','--project',proj,'--context','agent','--log-level','ERROR'])
    async with stdio_client(params) as (r,w):
        async with ClientSession(r,w) as s:
            await s.initialize()
            tools=await s.list_tools()
            t=[x for x in tools.tools if x.name=='get_symbols_overview'][0]
            print("schema:", json.dumps(t.inputSchema.get('properties',{}))[:300])
            for f in files:
                t0=time.time()
                res=await s.call_tool('get_symbols_overview', {'relative_path': f})
                txt=''.join(c.text for c in res.content if hasattr(c,'text'))
                print(f"\n=== {f} ({time.time()-t0:.1f}s, {len(txt)} chars)\n{txt[:1500]}")
asyncio.run(main())
