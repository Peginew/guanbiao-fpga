from pathlib import Path
import re,json,collections,hashlib,sys
R=Path(sys.argv[1]); DB=Path(sys.argv[2]); P=Path(r'C:/Users/Edward/Desktop/FPGA/MCU_Live_ROI_20261029/review_runtime/compact_physical_20261031_051722_529035')
old={'FF_and_module_cut_values':json.loads((Path(__file__).parent/'frontier_inspection.json').read_text(encoding='utf-8'))['cuts']}; C='\\u_meter_pair/pipeline/reader/live/capture/'
# Actual routed exported FF names shed the synthesis-only aliases on these two CDC taps.
# cr[1] is the healthy released CSI reset=1; release_sync[1] equals release_seen=0.
frontier_aliases={C+'cr[1]':C+'cr[1]_syn_3',C+'release_sync[1]':C+'release_sync[1]_syn_3'}
for actual,syn_name in frontier_aliases.items():
 assert syn_name in old['FF_and_module_cut_values']
 old['FF_and_module_cut_values'][actual]=old['FF_and_module_cut_values'][syn_name]
# SYN extractor overrides primary sr with rst_n; routed primary ASR uses cr[1].
# Preserve that same reset contract instead of tying the physical ASR deasserted.
old['FF_and_module_cut_values'][C+'cr[1]']='rst_n'
s=(R/'actual_netlist.v').read_text(encoding='utf8'); sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
pat=re.compile(r'^  (PH1P_[A-Za-z0-9_]+)\s*(?:#\((.*?)\)\s*)?(?://[^\n]*\n\s*)*(\\\S+|[A-Za-z_$][\w$]*)\s+\((.*?)\);',re.M|re.S)
cells=[]
for m in pat.finditer(s):
 ps={k:re.sub(r'\s+','',v) for k,v in re.findall(r'\.(\w+)\((.*?)\)(?:,|\s*$)',m[4],re.M)}
 pa=dict(re.findall(r'^\s*\.(\w+)\((.*?)\)(?:,|\s*$)',m[2]or'',re.M));cells.append(dict(type=m[1],name=m[3],ports=ps,params=pa))
q=lambda c,k,d:c['params'].get(k,'"'+d+'"').strip('"')
outs=['ofa','ofb','oqa','oqb','fco','fco_f','qci'];drivers={v:(i,k) for i,c in enumerate(cells) if c['type']=='PH1P_PHY_LSLICE' for k,v in c['ports'].items() if k in outs}
def ffkind(c,p):
 return 'A' if (p=='oqa' and q(c,'OQAMUX','RELUT6')=='QA') or (p=='ofb' and q(c,'OFB_SD','LUTX')=='QA') else 'B' if (p=='oqb' and q(c,'OQBMUX','RELUT6')=='QB') or (p=='ofa' and q(c,'OFA_SD','QB')=='QB') else None
primary=[drivers[C+'bad'],drivers[C+'diag_first_causes[7]']];assert all(ffkind(cells[i],p) for i,p in primary)
def support(val):
 w,b,d=re.fullmatch(r"(\d+)'([bhd])([0-9a-fA-F_]+)",val).groups();n=int(d.replace('_',''),{'b':2,'h':16,'d':10}[b]);return [j for j in range(5) if any(((n>>a)^(n>>(a^(1<<j))))&1 for a in range(32))]
def ab(c,b):
 ps=c['ports']; get=lambda k:ps.get(k,"1'b0")
 keys=['ia','ib',q(c,'LUT5A_SD0','IC').lower(),'id',q(c,'LUT5A_SD1','IE').lower()] if b=='A' else ['ia','ib','ic',q(c,'LUT5B_SD2','ID').lower(),'ie']
 if 'ft_lut5a' in keys:raise ValueError(('unsupportedFT',c['name']))
 return [get(keys[j]) for j in support(c['params'].get('INIT_LUT5'+b,"32'h00000000"))],tuple(get(k) for k in keys)
def lut(c,b):return ab(c,b)[0]
def six(c):
 a,am=ab(c,'A');b,bm=ab(c,'B');z=a+b
 if q(c,'LUTMODE','DLUT5')=='LUT6' and not (am==bm and c['params'].get('INIT_LUT5A')==c['params'].get('INIT_LUT5B')):z.append(c['ports'].get('imf',"1'b0"))
 return z if q(c,'LUTMODE','DLUT5')=='LUT6' else b
# Current UI checker derives cut values from its independently inspected actual SYN frontier.
# Physical LUT6 is the LUTX output in LUT6 mode. For DLUT5, LUT6 refers A for FF B? All actual queried FF B LUT6 data uses LUTX/B; six follows macro LUTX.
def carry(c):
 ps=c['ports'];z=lut(c,'A')
 if q(c,'ADDERMUX','0')=='IMB':z.append(ps.get('imb',"1'b0"))
 if q(c,'FCIMUX','0')=='FCI':z.append(ps.get('fci',"1'b0"))
 if q(c,'CIMUX','FIXED')=='MUX':z.append(ps.get('imc',"1'b0"))
 return z

def fun(c,p):
 if p=='ofa':
  t=q(c,'OFA_SD','QB');return lut(c,'A') if t=='LUT5A' else six(c) if t=='LUT6' else carry(c) if t=='F7CY' else []
 if p=='ofb':return carry(c) if q(c,'OFB_SD','LUTX')=='SUM' else six(c)
 if p in ('oqa','oqb'):return six(c)
 if p in ('fco','fco_f','qci'):return carry(c)
 raise ValueError(p)
def ffdeps(c,k):
 ps=c['ports'];t=q(c,'REG'+k+'_SD','OFA' if k=='A' else 'SUM')
 z=[ps.get('ima' if k=='A' else 'imb',"1'b0")] if t in ('IMA','IMB') else lut(c,'A') if t=='LUT5A' else fun(c,'ofa') if t=='OFA' else six(c) if t=='LUT6' else carry(c) if t=='SUM' else (_ for _ in ()).throw(ValueError(t))
 if q(c,'CE'+k+'MUX','0')=='SIG':z.append(ps.get('cea' if k=='A' else 'ceb',"1'b0"))
 return z
need=collections.defaultdict(set);leaves=set();todo=[]
for i,p in primary:
 need[i].add(p);todo+=ffdeps(cells[i],ffkind(cells[i],p))
seen=set()
while todo:
 n=todo.pop()
 if not n or "'" in n or n in seen:continue
 seen.add(n)
 if n not in drivers:leaves.add(n);continue
 i,p=drivers[n];c=cells[i]
 if ffkind(c,p):leaves.add(n);continue
 need[i].add(p);todo+=fun(c,p)
leaves-={C+'bad',C+'diag_first_causes[7]'}
cuts={}
for n in leaves:
 if n in old['FF_and_module_cut_values']:cuts[n]=old['FF_and_module_cut_values'][n]
 else:raise ValueError(('unclassified new leaf',n))
assert all(n.startswith(C) for n in cuts),[n for n in cuts if not n.startswith(C)]
selected=[cells[i] for i in need]
if '--dry' not in sys.argv:R.joinpath('cb33_route_guard_extract.json').write_text(json.dumps({'selected':selected,'needed_outputs':{cells[i]['name']:list(p) for i,p in need.items()},'leaves':sorted(leaves),'primary':[[cells[i],p] for i,p in primary],'cuts':cuts,'actual_netlist_sha256':sha(R/'actual_netlist.v')},indent=2),encoding='utf8')
print('EXTRACT',len(selected),'LEAVES',len(leaves),'PRIMARY',[(cells[i]['name'],p,ffkind(cells[i],p)) for i,p in primary])

if '--dry' not in sys.argv:
 # Keep original cell parameters and only the requested combinational output cones;
 # unrelated packed FF outputs are disconnected at the declared register frontier.
 pc=cells[primary[0][0]];fk=ffkind(pc,primary[0][1]);sd=q(pc,'REG'+fk+'_SD','OFA' if fk=='A' else 'SUM')
 direct=None;tap=None
 if sd in ('IMA','IMB'):direct=pc['ports'][sd.lower()]
 elif fk=='A' and sd=='OFA' and q(pc,'OFA_SD','QB') in ('LUT5A','LUT6'):tap='ofa'
 elif fk=='A' and sd=='LUT5A' and q(pc,'OFA_SD','QB')=='LUT5A':tap='ofa'
 elif fk=='B' and sd=='LUT6' and q(pc,'OFB_SD','LUTX')=='LUTX':tap='ofb'
 elif fk=='B' and sd=='SUM' and q(pc,'OFB_SD','LUTX')=='SUM':tap='ofb'
 else:raise ValueError(('no unchanged physical D tap',fk,sd,pc['params']))
 allnets=set(cuts)|{C+'bad',C+'diag_first_causes[7]'}
 for i in need:
  for v in cells[i]['ports'].values():
   if "'" not in v:allnets.add(v)
 if tap:
  dnet=pc['ports'].get(tap,'__actual_bad_D');allnets.add(dnet);need[primary[0][0]].add(tap)
 else:dnet=direct
 rename={n:'n'+str(i) for i,n in enumerate(sorted(allnets))}
 val=lambda v:rename[v] if v in rename else v
 lines=['`timescale 1ns/1ps','module cb33_routed_cone(input clk,rst_n,input[7:0]g,input[2:0]st,output bad_d,bad_q,diag_q);']
 lines+=['wire '+n+';' for n in rename.values()]
 usedinputs=set();usedout=set()
 for i in need:
  c=cells[i];pp=dict(c['ports']);keep=set(need[i]);isprimary=i in {j for j,k in primary}
  for k in list(pp):
   if k in outs and k not in keep:del pp[k]
  if i==primary[0][0] and tap:pp[tap]=dnet
  for k,v in pp.items():
   if k in outs:usedout.add(v)
   elif k not in ('clk',):usedinputs.add(v)
  if 'clk' in pp:pp['clk']='clk' if isprimary else "1'b0"
  if isprimary:assert q(c,'CLKMUX','0')=='SIG'
  pars=',\n'.join(' .'+k+'('+v+')' for k,v in c['params'].items())
  lines.append(c['type']+' #(\n'+pars+'\n) u'+str(i)+'(\n'+',\n'.join(' .'+k+'('+val(v)+')' for k,v in pp.items())+'\n);')
 for n,v in cuts.items():lines.append('assign '+rename[n]+' = '+v+';')
 for n in sorted(usedinputs-usedout-set(cuts)-{C+'bad',C+'diag_first_causes[7]'}):
  if n in rename:lines.append('assign '+rename[n]+" = 1'b0;")
 lines+=['assign bad_q='+rename[C+'bad']+';','assign diag_q='+rename[C+'diag_first_causes[7]']+';','assign bad_d='+val(dnet)+';','endmodule']
 tail=(P/'life32_guard_cone.sv').read_text();tail=tail[tail.index('module tb_'):].replace('life32_routed_cone','cb33_routed_cone').replace('LIFE32_ROUTED','CB33_ROUTED')
 lines.append(tail);(R/'cb33_guard_cone.sv').write_text('\n'.join(lines),encoding='utf8')
 cfg={'selected':[cells[i] for i in need],'needed_outputs':{cells[i]['name']:list(p) for i,p in need.items()},'leaves':sorted(leaves),'cuts':cuts,'unused_packed_inputs_tied0':sorted(usedinputs-usedout-set(cuts)-{C+'bad',C+'diag_first_causes[7]'}),'actual_netlist_sha256':sha(R/'actual_netlist.v'),'DB_sha256':sha(DB),'D_observation':{'kind':fk,'data_select':sd,'unchanged_tap':tap,'direct_net':direct},'TB_template':str(P/'life32_guard_cone.sv'),'TB_template_sha256':sha(P/'life32_guard_cone.sv')}
 (R/'cb33_guard_config.json').write_text(json.dumps(cfg,indent=2),encoding='utf8')
 print('EMITTED',R/'cb33_guard_cone.sv')
