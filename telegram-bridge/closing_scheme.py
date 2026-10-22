"""Prepare an auditable minimal transition change for the installation scheme."""
import copy

def plan(program):
    if str(program['id'])!='16':raise ValueError('Unexpected program')
    result=copy.deepcopy(program)
    changes={'263':('137','138','139')}
    remove={'264':('138','139'),'283':('136','137'),'309':('136','139')}
    transitions=[]
    for item in result['transitions']:
        key=str(item['id']);pair=(str(item['from']['id']),str(item['to']['id']))
        if key in remove or key in changes:
            if item.get('operation') or item.get('rule') or item.get('operations'):raise ValueError('Transition has business actions; preserve and review them first')
        if key in remove:
            if pair!=remove[key]:raise ValueError('Program changed since review')
            continue
        if key in changes:
            old=changes[key]
            if pair!=(old[0],old[1]) and pair!=(old[0],old[2]):raise ValueError('Program changed since review')
            item['to']['id']=old[2]
        transitions.append(item)
    pairs={(x['from']['id'],x['to']['id']) for x in transitions}
    if not {('136','138'),('138','137'),('137','139')}<=pairs:raise ValueError('Required transition missing')
    states=result['states'];ids=[str(x['id']) for x in states]
    if ids.index('138')>ids.index('137'):
        a,b=ids.index('138'),ids.index('137');states[a],states[b]=states[b],states[a]
    return {'contentType':'Program','id':'16','states':states,'transitions':transitions}
