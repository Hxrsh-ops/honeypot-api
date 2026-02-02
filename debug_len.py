from agent import Agent
s={}
a=Agent(s)
from collections import Counter
cnt=Counter()
for i in range(60):
    r=a.generate_reply('probe','Details please')
    rstr=r if isinstance(r, str) else r.get('reply')
    L=len(rstr)
    typ='long' if L>=100 else ('medium' if L>=40 else 'short')
    cnt[typ]+=1
    if i<12:
        print(i, typ, rstr)
print('counts', cnt)
