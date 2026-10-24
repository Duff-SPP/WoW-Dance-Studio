"""Conservative anatomical graph inference; no target bone indices or reference answers.

Key IDs 0..26 follow Elune m2_ui._KEY_BONE_NAMES. Other/custom IDs are
deliberately not interpreted. Scores rank evidence, not probabilities.
"""
import math

GENERATOR = 'anatomy-0.4.5'
ESSENTIAL = ['Root','pelvis','Spine_01','Spine_03','spine_05','neck_01','neck_02','head'] + [
    part+'_'+side for side in ('l','r') for part in ('clavicle','upperarm','lowerarm','hand','thigh','calf','foot','ball')]
KEYS = {'pelvis':26,'Spine_01':4,'head':6,'clavicle_l':2,'clavicle_r':3,'upperarm_l':0,'upperarm_r':1}


def infer(rig, attachments, overrides=None):
    bones={b['name']:b for b in rig['bones']}
    def chain(name):
        result=[]
        while name in bones and name not in result:
            result.append(name); name=bones[name]['parent']
        return result
    ancestors={name:chain(name) for name in bones}
    def common(names):
        return next((n for n in ancestors[names[0]] if all(n in ancestors[k] for k in names)),None) if names else None
    def key(k):
        return [n for n,b in bones.items() if int(b.get('properties',{}).get('m2_key_bone_id',-1))==k]
    attached={}
    for a in attachments:
        if a['parent']==rig['name'] and a['bone'] in bones:
            attached.setdefault(a['name'].split('_attach_')[-1].casefold(),[]).append(a['bone'])
    rows={}; mapping={}
    height=max((b['head'][2] for b in bones.values()),default=1)-min((b['head'][2] for b in bones.values()),default=0)
    tolerance=max(height*.005,1e-5)
    def propose(role,candidates,reason,anchor=False):
        candidates=list(dict.fromkeys(n for n in candidates if n in bones))
        rows[role]=dict(source=role,target=candidates[0] if len(candidates)==1 else None,
                        confidence='Strong' if len(candidates)==1 and anchor else 'Corroborated' if len(candidates)==1 else 'Ambiguous' if candidates else 'Missing',
                        evidence=[reason],alternatives=[dict(target=n,rank=i+1) for i,n in enumerate(candidates)])
        if len(candidates)==1: mapping[role]=candidates[0]
    def unsupported(role,reason):
        rows[role]=dict(source=role,target=None,confidence='Unsupported',evidence=[reason],alternatives=[])
    def proven_static_subtree(name):
        pending=[name]; seen=set()
        while pending:
            name=pending.pop()
            if name in seen: return False
            seen.add(name); bone=bones[name]
            if int(bone.get('properties',{}).get('m2_bone_flags',-1))!=0 or bone.get('m2_has_animation') is not False: return False
            pending.extend(bone['children'])
        return True
    for role,k in KEYS.items(): propose(role,key(k),'Semantic M2 key-bone ID '+str(k),True)
    if 'pelvis' in mapping:
        roots=ancestors[mapping['pelvis']][1:]
        propose('Root',roots[-1:] if roots else [],'Top ancestor of keyed pelvis; origin checked during validation')
        if not roots: unsupported('Root','Keyed pelvis is the skeletal root; use pelvis world displacement once, no duplicate assignment')
    for side,label,ids in [('l','left',range(13,18)),('r','right',range(8,13))]:
        fingers=[key(k)[0] for k in ids if len(key(k))==1]
        hand=common(fingers) if len(fingers)>=3 else None
        hand_attachments=attached.get('hand'+label,[])
        if hand is None and len(hand_attachments)==1 and fingers:
            for n in ancestors[hand_attachments[0]]:
                digits=[k for k in bones[n]['children'] if bones[k].get('skin_weight',0)>0]
                if bones[n].get('skin_weight',0)>0 and len(digits)>=2 and all(n in ancestors[f] for f in fingers):
                    hand=n; break
        candidates=[hand] if hand else []
        # Attachments corroborate a finger-chain-derived hand, not a nearest joint.
        att=attached.get('hand'+label,[])
        if hand and att and not all(hand in ancestors[a] for a in att): candidates=[]
        propose('hand_'+side,candidates,'Keyed finger-root ancestry, distal skinning branches and hand attachment agree ('+str(len(fingers))+' keyed roots)',len(fingers)>=3)
        if hand:
            upper=mapping.get('upperarm_'+side)
            shoulder=mapping.get('clavicle_'+side)
            if upper and shoulder and bones[hand]['parent']==upper and bones[upper]['parent']==shoulder and bones[shoulder]['parent']:
                # Older key tables may label elbow as Arm and shoulder as
                # Shoulder. Joint roles come from the complete digit/arm chain.
                elbow=attached.get('elbow'+label,[])
                if len(elbow)==1 and upper in ancestors[elbow[0]]:
                    propose('upperarm_'+side,[shoulder],'Semantic Arm is wrist-proximal/elbow-anchored; use proximal shoulder pivot as upper arm')
                    propose('clavicle_'+side,[bones[shoulder]['parent']],'Distinct proximal collar joint before shoulder/elbow/hand chain')
                    upper=shoulder
            if not key(KEYS['upperarm_'+side]):
                shoulder=mapping.get('clavicle_'+side)
                # Some older M2s label the upper-arm pivot Shoulder, omit Arm,
                # and have a distinct proximal collar joint on the hand path.
                if shoulder and shoulder in ancestors[hand] and bones[shoulder]['parent']:
                    parent=bones[shoulder]['parent']
                    if len([n for n in ancestors[hand] if shoulder in ancestors[n] and n!=shoulder])>=2:
                        propose('upperarm_'+side,[shoulder],'Missing Arm key; Shoulder key lies on distal hand chain with separate proximal collar joint')
                        propose('clavicle_'+side,[parent],'Proximal parent of semantic shoulder on connected hand chain')
                        upper=shoulder
            path=[n for n in ancestors[hand][1:] if upper and n!=upper and upper in ancestors[n]]
            elbows=attached.get('elbow'+label,[])
            if len(path)>1 and len(elbows)==1:
                lineage=[n for n in path if n in ancestors[elbows[0]]]
                if lineage: path=lineage[:1]
                distances=sorted((math.dist(bones[n]['head'],bones[elbows[0]]['head']),n) for n in path)
                if distances[0][0]<tolerance and (len(distances)==1 or distances[1][0]-distances[0][0]>tolerance): path=[distances[0][1]]
            propose('lowerarm_'+side,path[:1] if len(path)==1 else path,'Connected hand/upper-arm chain, corroborated by elbow ancestry where needed')
        feet=attached.get(label+'foot',[])
        ranked=[]
        if len(feet)==1:
            pivot=bones[feet[0]]['head']
            for distance,n in enumerate(ancestors[feet[0]]):
                b=bones[n]
                if math.dist(b['head'],pivot)>height*.08: break
                toe_children=[child for child in b['children'] if
                    bones[child]['head'][0]-b['head'][0]>tolerance and bones[child]['head'][2]<=b['head'][2]+tolerance
                    and bones[child]['head'][0]-b['head'][0] > .5*abs(bones[child]['head'][2]-b['head'][2])
                    and bones[child].get('skin_weight',0)>0
                    and int(bones[child].get('properties',{}).get('m2_bone_flags',0))&512]
                score=4*bool(toe_children)+2*bool(b.get('skin_weight',0))-.1*distance
                ranked.append(dict(target=n,score=score,evidence=dict(attachment_distance=distance,distal_deforming_children=toe_children,skin_weight=b.get('skin_weight',0))))
            ranked.sort(key=lambda row:row['score'],reverse=True)
        feet=[ranked[0]['target']] if ranked and ranked[0]['score']>=1.5 and (len(ranked)==1 or ranked[0]['score']-ranked[1]['score']>=1) else [r['target'] for r in ranked]
        propose('foot_'+side,feet,'Foot attachment ancestry, bounded pivot offset, directional distal chain and skin weights',True)
        rows['foot_'+side]['alternatives']=ranked
        foot=mapping.get('foot_'+side); pelvis=mapping.get('pelvis')
        if foot and pelvis:
            # Eliminate colocated helper joints, retain the proximal chain joints.
            path=[n for n in reversed(ancestors[foot][1:]) if n!=pelvis and pelvis in ancestors[n]]
            opposite=attached.get(('right' if side=='l' else 'left')+'foot',[])
            shared=common([foot,opposite[0]]) if len(opposite)==1 else None
            # A shared lower-body helper can sit substantially below the pelvis.
            # It cannot be either thigh: bilateral legs diverge below it.
            if shared:
                path=[n for n in path if n not in ancestors[shared]]
            usable=[]
            for n in path:
                if bones[n]['head'][2] < bones[pelvis]['head'][2]-.02*max(abs(bones[pelvis]['head'][2]),.01):
                    if bones[n].get('skin_weight',0)<=0 and int(bones[n].get('properties',{}).get('m2_key_bone_id',-1))<0: continue
                    if not usable or math.dist(bones[n]['head'],bones[usable[-1]]['head'])>tolerance:
                        usable.append(n)
            # Last colocated foot-parent is an ankle helper, not the knee.
            usable=[n for n in usable if math.dist(bones[n]['head'],bones[foot]['head'])>tolerance]
            knees=attached.get('knee'+label,[])
            if len(usable)>2 and len(knees)==1:
                near=[n for n in usable[1:] if n in ancestors[knees[0]]]
                near=near[-1:]
                if not near:
                    distances=sorted((math.dist(bones[n]['head'],bones[knees[0]]['head']),n) for n in usable[1:])
                    if distances[0][0]<height*.12 and (len(distances)==1 or distances[1][0]-distances[0][0]>tolerance): near=[distances[0][1]]
                if len(near)==1: usable=[usable[0],near[0]]
            propose('thigh_'+side,usable[:1] if len(usable)==2 else usable,'Bilateral leg divergence to foot: proximal separated descending joint')
            propose('calf_'+side,usable[1:] if len(usable)==2 else usable,'Bilateral leg divergence to foot: distal separated descending joint')
            candidates=[]
            for n,b in bones.items():
                if b['parent']==foot and b['head'][0]-bones[foot]['head'][0]>tolerance:
                    # Deforming, forward/downward toe base; no zero-flag sole helpers.
                    if int(b.get('properties',{}).get('m2_bone_flags',0)) & 512 and b['head'][2]<=bones[foot]['head'][2]+tolerance and b.get('skin_weight',0)>0:
                        candidates.append(n)
            propose('ball_'+side,candidates,'Deforming foot child below ankle, separated pivot (toe chain)')
            weighted_children=[k for k in bones[foot]['children'] if bones[k].get('skin_weight',0)>0]
            static_children=[k for k in weighted_children if proven_static_subtree(k)]
            if not candidates and not any(k not in static_children for k in weighted_children):
                unsupported('ball_'+side,'No independent toe joint: hoof terminates or its weighted children are proven static (zero flags and empty supplied animation tracks); preserve rest offsets and inherit hoof motion')
                rows['ball_'+side]['excluded_static_children']=static_children
            elif not candidates:
                rows['ball_'+side]['evidence'].append('Weighted child exists outside the plausible distal foot region; review source anatomy instead of guessing a toe')
    left=mapping.get('clavicle_l'); right=mapping.get('clavicle_r'); pelvis=mapping.get('pelvis')
    if pelvis:
        center=bones[pelvis]['head'][1]
        for part in ('thigh','calf'):
            for side,other in (('l','r'),('r','l')):
                role=part+'_'+side; partner=part+'_'+other
                if role in mapping or partner not in mapping or role not in rows: continue
                point=bones[mapping[partner]]['head']; mirrored=[point[0],2*center-point[1],point[2]]
                candidates=[a['target'] for a in rows[role]['alternatives'] if math.dist(bones[a['target']]['head'],mirrored)<tolerance]
                if len(candidates)==1:
                    propose(role,candidates,'Unique mirrored counterpart on the connected bilateral leg path; displaced knee attachment cannot override symmetry')
    chest=common([left,right]) if left and right else None
    if chest and pelvis:
        path=[n for n in reversed(ancestors[chest]) if n!=pelvis and pelvis in ancestors[n]]
        propose('spine_05',[chest],'Common ancestor of bilateral keyed shoulder chains')
        propose('Spine_03',path[1:2] if len(path)==3 else [],'Three-joint pelvis-to-shoulder axial chain, middle joint')
        if len(path) in (2,4): unsupported('Spine_03','No unique middle joint; mapped low spine/chest retain evaluated source rotations; intermediate target joints inherit')
        if mapping.get('Spine_01') and path and mapping['Spine_01']!=path[0]:
            rows['Spine_01']['confidence']='Ambiguous'; mapping.pop('Spine_01')
    head=mapping.get('head')
    if head and chest:
        neck=[n for n in reversed(ancestors[head][1:]) if n!=chest and chest in ancestors[n]]
        propose('neck_01',neck[:1] if len(neck)==2 else [],'Two-joint chest-to-keyed-head neck chain')
        propose('neck_02',neck[1:] if len(neck)==2 else [],'Two-joint chest-to-keyed-head neck chain')
        if len(neck)==1:
            propose('neck_01',neck,'Single joint on chest-to-head path')
            unsupported('neck_02','Target has one neck joint; no duplicate target assignment')
        elif not neck:
            unsupported('neck_01','Head directly descends from chest; no distinct neck joint')
            unsupported('neck_02','Head directly descends from chest; no distinct neck joint')
    for role in ESSENTIAL:
        if role not in rows: propose(role,[],'Insufficient anatomical evidence')
    for role,target in (overrides or {}).items():
        if role not in ESSENTIAL or target not in bones: raise ValueError('Invalid manual mapping: '+role+' -> '+str(target))
        mapping[role]=target
        rows[role].update(target=target,confidence='Manual',evidence=rows[role]['evidence']+['Explicit user correction'])
    # Store observable chain features rather than a fabricated probability.
    for role,n in mapping.items():
        rows[role]['features']=dict(parent=bones[n]['parent'],position=bones[n]['head'],length=bones[n]['length'],
                                    skin_weight=bones[n].get('skin_weight',0),children=len(bones[n]['children']))
    return mapping,list(rows.values())
