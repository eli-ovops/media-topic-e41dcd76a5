#!/usr/bin/env python3
"""Regenerate a read-only index from canonical local sources. Never writes inputs."""
from pathlib import Path
import json, hashlib, re, datetime, os
from functools import lru_cache

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[1]
FRED=Path('/Users/USER/.codex/skill-repos/FredTalk')
SY=Path('/Users/USER/.codex/skills/sy-styles-20/references/repository')
CARDS=ROOT/'Fred付费资料全站学习-20261016/研读/01/组件调用库'
assets=json.loads((ROOT/'资产库/FredTalk/manifest.json').read_text())['assets']
current=json.loads((FRED/'library/catalog.json').read_text())
routes=json.loads((FRED/'library/routes.json').read_text())
allow={}; checks=[]
@lru_cache(maxsize=None)
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def link(path,label=None,expected=None):
 p=Path(path); exists=p.is_file()
 row={'path':str(p),'label':label or p.name,'exists':exists}
 if exists:
  real=p.resolve(); key=hashlib.sha256(str(real).encode()).hexdigest()[:24]
  st=real.stat(); row.update(url='/asset/'+key,bytes=st.st_size,realpath=str(real))
  digest=sha(real)
  row['sha256']=digest
  if expected: row['expected_sha256']=expected;row['hash_match']=digest==expected
  allow[key]={'path':str(real),'bytes':st.st_size,'mtime_ns':st.st_mtime_ns,'sha256':digest}
 checks.append(row)
 return row
cards={}
for p in CARDS.glob('*.json'):
 d=json.loads(p.read_text())
 if 'filename' in d and 'card_key' in d: cards[d['filename']]=(p,d)
rows=[]
byid={x['id']:x for x in current['items']}
for a in assets:
 p,c=cards[a['filename']]
 api=c.get('source_api',{})
 for k in ['source_path','source_sha256','kit']:
  if k not in c and k in api:c[k]=api[k]
 for k,sub,field in [('use','usage','suitable'),('avoid','usage','avoid'),('capacity','usage','capacity'),('entry','handoff','entry'),('exit','handoff','exit')]:
  if k not in c:c[k]=c.get(sub,{}).get(field,'')
 row=dict(key='fred-preview:'+a['filename'],id=a['component_id'],label=a['label'],title=a['title'],source='Fred 归档预览',group=a['collection_id'],category=a['category'],description=a['description_from_catalog'],use=c.get('use',''),entry=c.get('entry',''),exit=c.get('exit',''),avoid=c.get('avoid',''),capacity=c.get('capacity',''),variant=c['card_key'],filename=a['filename'],seconds=c.get('seconds'),current_catalog=a['component_id'] in byid,import_render='本期未 import / 渲染',evidence='沿用既有调用卡；历史全时段采样不等于连续看听。',media=link(a['file'],'原预览 MP4',a['sha256']),card=link(p.with_suffix('.md'),'准确调用卡'),card_json=link(p,'调用卡 JSON'),sources=[],kits=[])
 if c.get('source_path'): row['sources'].append(link(c['source_path'],'准确实现',c.get('source_sha256')))
 for s in api.get('sources',[]):
  sp=s.get('absolute_path')
  if sp and sp not in [x['path'] for x in row['sources']]:row['sources'].append(link(sp,Path(sp).name,s.get('sha256')))
 for k in c.get('kit',[]):
  if isinstance(k,dict) and k.get('path'): row['kits'].append(link(k['path'],Path(k['path']).name,k.get('sha256')))
 row['status']='有本地预览' if row['media']['exists'] else '预览缺失'
 row['group']=row['group'] or c.get('source_package') or '原公开场景归档（见准确调用卡）'
 row['search']=' '.join(str(c.get(k,'')) for k in ['use','avoid','capacity','entry','exit','cue','props','description_from_catalog'])
 rows.append(row)
ids={a['component_id'] for a in assets}
bindings={}
for item in current['items']:
 resolved=[]
 for s in item.get('sources',[]):
  rel=routes.get(s.get('url')) or s.get('installPath')
  if rel:
   path=FRED/rel
   resolved.append(link(path,s.get('label'),s.get('sha256')) if path.is_file() else {'path':str(path),'label':s.get('label'),'exists':False,'state':'主Skill仓库无此文件；对应归档实现单独列出'})
 bindings[item['id']]={'id':item['id'],'label':item['label'],'sources':resolved,'installed_any':any(z['exists'] for z in resolved),'installed_all':bool(resolved) and all(z['exists'] for z in resolved)}
for row in rows:
 row['current_installation']=bindings.get(row['id'])
extras=[x for x in current['items'] if x['id'] not in ids]
for x in extras:
 src=[]
 for s in x.get('sources',[]):
  rel=routes.get(s.get('url')) or s.get('installPath')
  if rel:
   z=link(FRED/rel,s.get('label'),s.get('sha256'))
   if z['path'] not in [v['path'] for v in src]:src.append(z)
 media=None
 for v in x.get('previews',[]):
  if v.get('privacyExcluded'):continue
  rel=routes.get(v.get('videoUrl'))
  if rel and (FRED/rel).is_file():media=link(FRED/rel,'本地预览',v.get('sha256'));break
 m=x.get('matching',{})
 rows.append(dict(key='fred-catalog:'+x['id'],id=x['id'],label=x['label'],title=x['title'],source='Fred catalog 额外',group=x.get('collectionId') or x.get('origin','当前 catalog'),category=x.get('category','讲解段落'),description=x.get('description',''),use=m.get('action',''),entry='暂无本库逐项调用卡；按准确项目入口核参数。',exit='需在本期定义对象交接并验实际导出。',avoid='不得把源码存在当成运行通过。',capacity='',variant=x['referenceId'],filename='',current_catalog=True,media=media,sources=src,kits=[],status='有本地预览' if media else '仅源码 / 预览缺口',import_render='本期未 import / 渲染',evidence='当前 catalog 元数据；未复查完整动态。预览 privacy-excluded 标记予以保留。',search=json.dumps(m,ensure_ascii=False)))
# Parse inert metadata only. Do not execute the source repository.
meta=(SY/'comp/meta.js').read_text()
meta2=(SY/'vol2/comp/meta.js').read_text()
for chunk in re.split(r'\{ id:',meta)[1:]:
 def field(name):
  m=re.search(r"\b"+name+r":\s*'([^']*)'",chunk);return m.group(1) if m else ''
 num=re.match(r"\s*'([^']+)'",chunk).group(1);dirname=field('dir')
 names=re.search(r'zh:\s*\[([^]]+)\]',chunk).group(1)
 title=' / '.join(re.findall(r"'([^']+)'",names));desc=field('desc')
 tags=re.search(r'tags:\s*\[([^]]+)\]',chunk).group(1)
 sources=[link(SY/'styles'/dirname/'index.html','第一期 HTML 源码'),link(SY/'vol2/styles'/dirname/'index.html','第二期 HTML 源码')]
 chunk2=next((q for q in re.split(r'\{ id:',meta2)[1:] if re.match(r"\s*'"+num+"'",q)), '')
 desc2=re.search(r"desc:\s*'([^']*)'",chunk2)
 rows.append(dict(key='sy:'+dirname,id='sy:'+dirname,label='SY '+num,title=title,source='sy 20 种机制',group='sy-styles-20 · 两期源码分别列出',category='代码风格与机制',description=desc,use=desc,entry='沿同一对象、材质与镜头建立关系；具体入场见所选期源码。',exit='按本期内容定义落定状态和下一镜的接管对象。',avoid='源码不是已验 MP4；第二期场景不同，不能替换第一期编号即认定同效果。',capacity='',variant=dirname,filename=dirname+'/index.html',media=None,sources=sources,kits=[link(SY/'lib/core.js','第一期 core.js'),link(SY/'vol2/lib/core.js','第二期 core.js')],status='源码 / 示例，暂无本地 MP4',import_render='本期未 import / 渲染',evidence='两期源码实际存在；本轮未运行源 HTML。',search=tags+' '+(desc2.group(1) if desc2 else ''),second_series_description=desc2.group(1) if desc2 else '详见第二期源码'))

# Explicit task-related skills, not an inventory of all installed tools.
definitions={
 'eli-media-workflow':('流程','全流程责任与授权入口','接收选题、素材、制作或发布任务时先核当前阶段。'),
 'fred-remotion-output':('主制作','组件选型、对象交接、完整视频与局部返修','有冻结口播和素材，需要编排与实际输出时。'),
 'fred-remake':('Fred 专项','准确参考复刻与场景实现','需要保留某个成熟组件的准确动作与质感时。'),
 'body-text-motion-effects':('Fred 专项','正文文字动效','正文出现、强调和衔接时，避免通用大字页。'),
 'fredtalk-deck-motion-pipeline':('Fred 专项','旧 Deck 动效流程参考','仅明确采用旧工程时查，不与当前主流程同时启动。'),
 'frame-smith':('动效辅助','节拍与运动质感','需要辅助镜头节奏时，服从当前 Fred/sy 实现。'),
 'sy-styles-20':('sy','20种代码风格与两期场景源码','按内容选择页面推镜、版面阅读、蓝图组装等动作。'),
 'audio-subtitle-roughcut':('声音与剪辑','音频、字幕驱动粗剪','接收真实口播后核时钟、切点及字幕；ASR不等于听音。'),
 'talking-head-recut':('声音与剪辑','口播重剪','局部口播修剪、停顿与内容顺序调整。'),
 'video-edit':('声音与剪辑','视频编辑与组合','已有素材需要剪辑、拼接与导出时。'),
 'embedded-captions':('声音与剪辑','字幕嵌入','字幕落位与画面避让时。'),
 'eli-cover-production':('封面','Eli封面与四比例适配','封面、身份参考图、改图与比例重排。'),
 'imagegen':('封面','内置图像生成与修改','按封面任务约束编辑图像，原文与实际工具分开。'),
 'media-use':('质检与媒体','实际媒体读取与证据边界','读取视频前核可用能力；采样、转录和连续看听分开。'),
 'general-video':('质检与媒体','视频任务方法','按具体视频任务补充入口，不取代本项目唯一流程。'),
 'hyperframes':('其他已装制作工具','HTML时间轴视频入口','当前任务明确选用 Hyperframes 时。'),
 'hyperframes-core':('其他已装制作工具','时间轴基础','Hyperframes 工程组织与核心契约。'),
 'hyperframes-animation':('其他已装制作工具','动画编排','Hyperframes 动画实现。'),
 'hyperframes-audio':('其他已装制作工具','音频同步','Hyperframes 声音与时间轴。'),
 'hyperframes-cli':('其他已装制作工具','渲染命令入口','授权 Hyperframes 本地输出时。'),
 'hyperframes-keyframes':('其他已装制作工具','关键帧','Hyperframes 关键状态控制。'),
 'hyperframes-registry':('其他已装制作工具','组件检索','Hyperframes 组件和注册资料。'),
 'hyperframes-creative':('其他已装制作工具','视觉编排参考','Hyperframes 选型与创意阶段。'),
 'lemo-opuscar':('参考资料','电影视觉语言与导演方法库','找视觉语言和镜头方法；未安装完整运行时。'),
 'awesome-opus5-5-videos':('参考资料','有原始来源的动画提示词案例','按主题找少量参考；提示词不算可执行组件。'),
 'pdoom-video':('参考资料','章节接力与确定性时间轴示例','研究对象和镜头如何连续；不自动运行整片。'),
 'opus-video-prompts':('参考资料','中文友好视频提示词案例','按主题检索提示词并改为本期动作要求；本轮仅整理入口，未重读全库。'),
 'cloud-render':('其他已装制作工具','云端输出资料','仅有明确云端和费用授权时；本次未调用。'),
 'motion-design':('动效辅助','动效设计','按需补充运动职责与节奏设计。'),
 'animations':('动效辅助','动画交互实现参考','局部动效实现需要时；不代替视频实际导出。')}
skillroots=[Path('/Users/USER/.codex/skills'),ROOT/'.agents/skills',Path('/Users/USER/.agents/skills')]
skills=[]
for name,(cat,desc,when) in definitions.items():
 paths=[r/name/'SKILL.md' for r in skillroots]
 if name=='imagegen': paths.insert(0,Path('/Users/USER/.codex/skills/.system/imagegen/SKILL.md'))
 versions=[]
 for p in paths:
  if not p.is_file():continue
  v=link(p,str(p));v['symlink_or_parent_link']=str(p)!=str(p.resolve())
  txt=p.read_text();v['version_markers']=list(dict.fromkeys(re.findall(r'(?:ELI|CODEX|MOTION)[A-Za-z0-9_-]*20\d{6}[A-Za-z0-9_-]*',txt)))
  versions.append(v)
 if versions:skills.append(dict(key=name,title=name,category=cat,description=desc,when=when,versions=versions,unique_realpaths=len({v['realpath'] for v in versions}),unique_hashes=len({v['sha256'] for v in versions}),read_scope='索引元信息与原文入口，不声明本次全文执行/运行通过'))
# Preserve nested original code-video skill variants explicitly.
for p in [SY/'SKILL.md',SY/'styles/SKILL.md',SY/'skills/sy-styles-20/SKILL.md']:
 skills.append(dict(key='code-video:'+str(p.relative_to(SY)),title='code-video / '+str(p.relative_to(SY)),category='sy',description='sy仓库原始Skill变体',when='按所选期与准确源码配套读取，避免同名Skill混用。',versions=[link(p)],unique_realpaths=1,unique_hashes=1,read_scope='提供原文，不运行仓库命令'))
guides=[link(ROOT/'资产库/FredTalk'/n,n) for n in ['调用入口.md','333组件总览.md','全库调用指南.md','制作前易错点.md']]
guides += [link(OUT/'本期粗糙问题与改进.md','本期粗糙问题与改进（PMO）'),link(Path('/Users/USER/.codex/skills/fred-remotion-output/references/eli-production-method.md'),'固定制作方法'),link(Path('/Users/USER/.codex/skills/fred-remotion-output/references/eli-rework-control.md'),'返修减耗方法')]
stats={'records':len(rows),'fred_preview_records':len(assets),'fred_preview_unique_ids':len(ids),'fred_current_catalog_records':len(current['items']),'fred_current_matched_ids':sum(x['id'] in ids for x in current['items']),'fred_catalog_extra_records':len(extras),'archived_only_ids':len(ids-set(byid)),'sy_mechanisms':20,'sy_source_variants':40,'local_preview_files':sum(bool(r.get('media') and r['media']['exists']) for r in rows),'call_cards':sum(bool(r.get('card') and r['card']['exists']) for r in rows),'records_with_source':sum(any(s['exists'] for s in r['sources']) for r in rows),'skill_entries':len(skills),'skill_locations':sum(len(s['versions']) for s in skills),'skill_unique_files':len({v['realpath'] for s in skills for v in s['versions']}),'missing_references':sum(not c['exists'] for c in checks),'hash_mismatches':sum(c.get('hash_match') is False for c in checks)}
data={'generated_at':datetime.datetime.now().astimezone().isoformat(),'stats':stats,'components':rows,'skills':skills,'guides':guides,'catalog_archived_items':current.get('archivedItems',[]),'limits':['333条历史采样研读不等于连续看听；本次未重复全库采样。','当前catalog有316条；预览库与catalog并集336个Fred ID，含双版本共338条记录。','sy按20种机制列出两期40份HTML，没有新做MP4。','703条提示词为参考材料，不计组件，不声明全文已读。','本期没有import、渲染或全库运行验收；原文的作者默认值/旧角色规则不覆盖当前项目要求。']}
stats['current_catalog_with_installed_sources']=sum(v['installed_any'] for v in bindings.values())
stats['current_catalog_using_archive_sources']=sum(not v['installed_any'] for v in bindings.values())
data['current_catalog_source_bindings']=list(bindings.values())
data['limits'].append('当前主Skill仓库源码211条；另105条从已归档会员源码取用，不能合称全部已在主仓库安装。')
(OUT/'catalog.json').write_text(json.dumps(data,ensure_ascii=False,indent=2))
(OUT/'allowlist.json').write_text(json.dumps(allow,ensure_ascii=False,indent=2))
(OUT/'reference-checks.json').write_text(json.dumps({'stats':stats,'references':checks},ensure_ascii=False,indent=2))
(OUT/'组件索引.md').write_text('# 组件索引\n\n由 build_catalog.py 读取原清单与调用卡生成；不另设长期事实源。\n\n'+'\n'.join('## '+r['label']+' · '+r['title']+'\n\n- 准确变体：'+r['variant']+'\n- 来源：'+r['source']+' / '+r['group']+'\n- 用途：'+r['use']+'\n- 状态：'+r['status']+'；'+r['import_render']+'\n'+ '\n'.join('- ['+x['label']+']('+x['path']+')' for x in ([r.get('media'),r.get('card')]+r['sources']+r['kits']) if x) for r in rows))
(OUT/'Skills索引.md').write_text('# 视频制作 Skills 索引\n\n全局/项目位置逐项核实，SHA相同不代表所有版本可互换；原文规则服从当前任务。\n\n'+'\n'.join('## '+s['title']+'\n\n'+s['description']+'。使用时机：'+s['when']+'\n\n'+ '\n'.join('- ['+v['path']+']('+v['path']+')\n  - 实体：'+v['realpath']+'\n  - SHA256：'+v['sha256'] for v in s['versions'])+'\n\n实体数：'+str(s['unique_realpaths'])+'；内容哈希数：'+str(s['unique_hashes'])+'。\n' for s in skills))
sop=Path('/Users/USER/.codex/skills/website-delivery-sop/references/DS-002B_website_delivery_sop_v2.md')
(OUT/'规则读取回执.json').write_text(json.dumps({'sop':str(sop),'sha256':sha(sop),'mtime_ns':sop.stat().st_mtime_ns,'read_lines':'1-2303 complete','scope':'04 execution, L0 local read-only catalogue; task explicitly chooses minimal standard static script instead of production stack','routing':'ROUTING-2026-10-13-v4','target':'gpt-6-astra/medium','actual_model':'UNKNOWN','actual_effort':'UNKNOWN','actual_speed':'UNKNOWN','weekly_remaining_reported':'6%','five_hour_remaining':'UNKNOWN','ordinaryUsageAllowed':True},ensure_ascii=False,indent=2))
print(json.dumps(stats,ensure_ascii=False,indent=2))
