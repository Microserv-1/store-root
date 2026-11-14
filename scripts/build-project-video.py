"""Build a labelled 1–2 minute project video locally from recorded evidence.

No AWS calls, workloads, browser automation, cloned voices or student impersonation.
Requires ffmpeg/ffprobe and requirements-video.txt; narrated mode also uses Windows TTS.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path
import shutil
import subprocess
import textwrap

from PIL import Image, ImageDraw, ImageFont

ROOT=Path(__file__).resolve().parents[1]
WIDTH,HEIGHT=1920,1080
BG='#0c1729'; PANEL='#14253c'; WHITE='#f3f7ff'; MUTED='#afc1d8'; BLUE='#5dc7ff'; GREEN='#63dfbb'

def font(size,bold=False):
    return ImageFont.truetype('C:/Windows/Fonts/segoeuib.ttf' if bold else 'C:/Windows/Fonts/segoeui.ttf',size)

def text(draw,xy,value,size=36,fill=WHITE,bold=False):
    draw.text(xy,value,font=font(size,bold),fill=fill)

def lines(draw,xy,value,width=48,size=34,fill=MUTED,gap=13):
    x,y=xy
    for row in textwrap.wrap(value,width=width):
        text(draw,(x,y),row,size,fill)
        y+=size+gap
    return y

def card(draw,box,title,detail,color=BLUE):
    draw.rounded_rectangle(box,radius=22,fill=PANEL,outline='#2c4767',width=2)
    x,y=box[0]+28,box[1]+23
    text(draw,(x,y),title,35,color,True)
    lines(draw,(x,y+60),detail,width=max(15,int((box[2]-box[0]-56)/18)),size=29)

def draw_scene(scene,index,evidence,silent=False):
    image=Image.new('RGB',(WIDTH,HEIGHT),BG);d=ImageDraw.Draw(image)
    text(d,(100,55),'MICROSERV STORE  /  PLATFORMS, MICROSERVICES, DEVOPS AND APIs',25,MUTED)
    text(d,(100,112),scene['title'],68,WHITE,True)
    d.line((100,220,1820,220),fill=BLUE,width=3)
    kind=scene['id']
    if kind=='intro':
        text(d,(100,300),'6 serviços integrados',91,WHITE,True)
        text(d,(100,425),'Amazon EKS · RDS · Jenkins',58,BLUE,True)
        lines(d,(105,545),'Yuri Henrique · Pessoa A / Gustavo Lina · Pessoa B',width=75,size=38)
        card(d,(1040,620,1815,860),'Validação real no EKS','40 verificações aprovadas\n14 de novembro de 2026'.replace('\n',' · '),GREEN)
        text(d,(105,770),'Escopo técnico e autoria documentados',34,MUTED)
    elif kind=='architecture':
        card(d,(100,280,600,470),'Gateway · Go','Entrada autenticada da aplicação')
        card(d,(710,280,1210,470),'Auth · Java','Spring Boot · validação JWT')
        card(d,(1320,280,1820,470),'Account · Python','FastAPI · identidade e credenciais')
        d.line((605,356,700,356),fill=BLUE,width=5)
        d.line((1215,356,1310,356),fill=BLUE,width=5)
        for box,title,detail in [((100,510,600,700),'Product','Produtos + Redis'),((710,510,1210,700),'Order','Pedidos USD + RabbitMQ'),((1320,510,1820,700),'Exchange · Python','Provedor externo de câmbio')]:
            card(d,box,title,detail,GREEN)
        card(d,(100,750,910,935),'Amazon EKS + RDS','Serviços no mesmo cluster · bancos isolados')
        card(d,(1010,750,1820,935),'CI/CD + observabilidade','Jenkins · imagens versionadas · Prometheus/Grafana')
    elif kind=='flow':
        steps=[('1','Cadastro / login','Token inválido → 401'),('2','Produto / pedido','Criação → 201'),('3','Propriedade','Outra conta → 404')]
        for i,(n,title,detail) in enumerate(steps):
            x=100+i*590
            card(d,(x,290,x+545,520),n+'  '+title,detail)
        text(d,(115,610),'USD 26,44',86,WHITE,True)
        text(d,(710,625),'→',80,BLUE)
        text(d,(960,610),'BRL 150,08',86,GREEN,True)
        lines(d,(120,755),'Cotação externa desta rodada · valor USD preservado · 40 verificações reais',width=85,size=35)
        text(d,(120,860),'Resultados registrados; não é uma nova chamada à API.',27,MUTED)
    elif kind=='bottlenecks':
        card(d,(100,285,910,530),'A · Observabilidade','Métricas, logs e diagnóstico de CPU em Account')
        card(d,(1010,285,1820,530),'A · Balanceamento','Três pods atendendo verificações de credenciais')
        card(d,(100,600,910,845),'B · Cache Redis','HIT, BYPASS e invalidação após exclusão',GREEN)
        card(d,(1010,600,1820,845),'B · Mensageria','Broker real e replay idempotente da notificação',GREEN)
        text(d,(110,900),'Código e evidências mantêm a autoria individual de cada integrante.',29,MUTED)
    elif kind=='business':
        text(d,(120,285),'Usuários',38,MUTED,True);text(d,(590,285),'Requisições',38,MUTED,True)
        text(d,(1120,285),'p95',38,MUTED,True);text(d,(1540,285),'Erros',38,MUTED,True)
        for i,(users,count,p95) in enumerate([(1,127,416),(4,508,414),(8,976,434)]):
            y=385+i*130
            d.rounded_rectangle((100,y-10,1820,y+95),radius=16,fill=PANEL)
            for x,value,color in [(140,str(users),WHITE),(620,str(count),WHITE),(1120,str(p95)+' ms',BLUE),(1560,'0%',GREEN)]:text(d,(x,y),value,54,color,True)
        text(d,(120,810),'1.611 requisições medidas · 60s por estágio',46,WHITE,True)
        text(d,(120,885),'Modelo fechado · pausa de 500 ms · até 2 POSTs de pedido por usuário',28,MUTED)
    elif kind=='hpa':
        graph=Image.open(evidence/'hpa/hpa-analysis.png').convert('RGB')
        graph.thumbnail((1250,705))
        image.paste(graph,(100,270))
        text(d,(1430,290),'2 → 5 → 2',61,GREEN,True)
        lines(d,(1410,400),'réplicas prontas de Account',width=18,size=36)
        text(d,(1410,545),'540 logins',50,WHITE,True)
        text(d,(1410,625),'0 erros',45,GREEN,True)
        text(d,(1410,705),'p95: 1,16 s',41,BLUE,True)
        lines(d,(1410,805),'Tráfego desigual; sem aumento de máquinas.',width=25,size=27)
    elif kind=='conclusion':
        card(d,(100,285,910,515),'Capacidade revisada','2 × t3a.medium no EKS · Jenkins t3a.small')
        card(d,(1010,285,1820,515),'US$ 6,89/dia','Estimativa fixa · variáveis adicionais',GREEN)
        lines(d,(115,595),'Limites: acesso privado, banco Single-AZ e NAT único. Teste curto não comprova SLA mensal.',width=85,size=39)
        text(d,(115,775),'microserv-1.github.io/store-docs-a',52,BLUE,True)
        text(d,(115,870),'Código · documentação · relatórios · vídeos',33,MUTED)
    d.line((100,980,1820,980),fill='#2b4261',width=2)
    label='VÍDEO SEM NARRAÇÃO' if silent else 'NARRAÇÃO SINTÉTICA'
    text(d,(100,1002),label+' · EVIDÊNCIAS REAIS REGISTRADAS EM 14/11/2026',23,MUTED)
    text(d,(1710,1000),f'{index+1:02}/07',27,BLUE,True)
    return image

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',default='artifacts/project-video')
    parser.add_argument('--silent',action='store_true',help='No speech synthesis and no audio track')
    args=parser.parse_args()
    out=Path(args.output).resolve();out.mkdir(parents=True,exist_ok=True)
    ffmpeg=shutil.which('ffmpeg');ffprobe=shutil.which('ffprobe')
    if not ffmpeg or not ffprobe:raise RuntimeError('ffmpeg and ffprobe are required')
    config=ROOT/'presentation/project-video.json'
    data=json.loads(config.read_text(encoding='utf-8'))
    evidence=ROOT/'docs/site/docs/evidence/2026-11-14-eks'
    summary=json.loads((evidence/'hpa/summary.json').read_text())
    business=json.loads((evidence/'business-summary.json').read_text())
    assert summary['requests']==540 and summary['scale_cycle_observed'] and summary['error_ratio']==0
    assert business['total_requests']==1611
    if not args.silent:
        subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(ROOT/'scripts/narrate-project-video.ps1'),'-NarrationFile',str(config),'-OutputDirectory',str(out)],check=True)
    durations=[]
    for i,scene in enumerate(data['scenes']):
        draw_scene(scene,i,evidence,args.silent).save(out/(scene['id']+'.png'))
        duration=[12,20,18,18,14,20,14][i] if args.silent else float(subprocess.check_output([ffprobe,'-v','error','-show_entries','format=duration','-of','default=noprint_wrappers=1:nokey=1',str(out/(scene['id']+'.wav'))],text=True))
        durations.append(duration)
    # Keep the final presentation under two minutes without clipping speech.
    speed=1.0 if args.silent else max(1.0,sum(durations)/112)
    segments=[];timeline=[];elapsed=0
    for scene,duration in zip(data['scenes'],durations):
        length=duration if args.silent else duration/speed+.65
        destination=out/(scene['id']+'.mp4')
        command=[ffmpeg,'-y','-hide_banner','-loglevel','error','-loop','1','-framerate','25','-i',str(out/(scene['id']+'.png'))]
        if not args.silent:command+=['-i',str(out/(scene['id']+'.wav')),'-af',f'atempo={speed},apad']
        command+=['-t',str(length),'-c:v','libx264','-preset','veryfast','-crf','21','-pix_fmt','yuv420p']
        command+=['-an'] if args.silent else ['-c:a','aac','-b:a','160k','-ar','48000']
        subprocess.run(command+[str(destination)],check=True)
        timeline.append({'id':scene['id'],'start_s':elapsed,'duration_s':length,'description':scene['narration'],'narration':None if args.silent else scene['narration']})
        elapsed+=length;segments.append(destination)
    listing=out/'segments.txt';listing.write_text(''.join("file '"+p.name+"'\n" for p in segments),encoding='utf-8')
    destination=out/'project-presentation.mp4'
    subprocess.run([ffmpeg,'-y','-hide_banner','-loglevel','error','-f','concat','-safe','0','-i',str(listing),'-c','copy','-movflags','+faststart',str(destination)],check=True)
    result=json.loads(subprocess.check_output([ffprobe,'-v','error','-show_entries','format=duration,size:stream=codec_type,width,height','-of','json',str(destination)],text=True))
    actual=float(result['format']['duration']);assert 60<=actual<=120,result
    if args.silent:assert not any(s['codec_type']=='audio' for s in result['streams'])
    manifest={'title':data['title'],'authors':data['authors'],'voice':None if args.silent else 'Microsoft Maria Desktop; synthetic, not either student','silent':args.silent,'evidence_date':data['evidence_date'],'duration_s':actual,'bytes':int(result['format']['size']),'sha256':hashlib.sha256(destination.read_bytes()).hexdigest(),'audio_tempo_multiplier':speed,'scenes':timeline,'limitations':'Edited presentation of recorded real evidence; no new live demo or AWS workload. Does not claim human participation or oral validation. Captions have approximate sentence timing and describe the scenes; they do not imply speech in silent mode.','source_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (config,Path(__file__),ROOT/'scripts/narrate-project-video.ps1',evidence/'hpa/summary.json',evidence/'business-summary.json',evidence/'business-integration.json')}}
    (out/'provenance.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    def stamp(seconds):
        millis=round(seconds*1000)
        return f'{millis//3600000:02}:{millis//60000%60:02}:{millis//1000%60:02}.{millis%1000:03}'
    captions=['WEBVTT','']
    for scene in timeline:
        sentences=re.split(r'(?<=[.!?])\s+',scene['description'])
        total=sum(len(s.split()) for s in sentences);cursor=scene['start_s']
        for sentence in sentences:
            length=(scene['duration_s']-.65)*len(sentence.split())/total
            captions.extend([stamp(cursor)+' --> '+stamp(cursor+length),sentence,''])
            cursor+=length
    (out/'captions.pt.vtt').write_text('\n'.join(captions),encoding='utf-8')
    print(json.dumps({'video':str(destination),'duration_s':actual,'voice':manifest['voice'],'size_bytes':manifest['bytes']},indent=2))

if __name__=='__main__':main()
