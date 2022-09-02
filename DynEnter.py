from pyparsing import *
import sys
import os
import re
from enum import IntEnum
import argparse

#TODO: save cordon information for later vscript use. 

cfg_skip_named_ents  = True #especially important to skip named entities when they have a movechild. dunno how to efficiently search if entity has movechild in entdata yet so, for now just skip named ents
#cfg_skip_infodecal  = True
cordonprefix    = "dynenter_"

area_info = []      #area info example: ['outside', ['(-4596 -7322 -834)', '(-408 2192 4620.05)', <entitycount>]
str_areafuncs = []
must_precache_mat = [] #If not precached before create, entities using these assets fail to load.

class AreaInfo(IntEnum):
    name = 0
    min_vec = 1
    max_vec = 2
    area_entcount = 3


classnames = [
    "prop_physics",
    "prop_physics_override",
    "prop_physics_multiplayer",
    "prop_dynamic",
    "prop_dynamic_override",
    "env_sprite",
    "keyframe_rope",
    "infodecal"
]
entfound_count = [0] * len(classnames) #store results based on classnames indexes



#find cordons with name DynEnter_*, put name, box in list 
#during analyzation of entities, move found entities in cordon groups. If not within cordon, skip entity
#for proper execution, install this in nmrih/bin/dynamicspawns






parser = argparse.ArgumentParser(prog='DynEnter',
                usage='%(prog)s [-game <game_directory> , -f <vmf_file>]',
                description='List the content of a folder')
parser.add_argument('-game',    type=str,           help='game directory')
parser.add_argument('-file',    type=str,           help='vmf map file to precompile')
parser.add_argument('-p',       action='store_true',help='[optional] compilepal plugin flag')
args = parser.parse_args()


if not os.path.isdir(args.game): 
    print("-game directory given does not exist.")
    sys.exit(1)
if not os.path.exists(args.game + "/gameinfo.txt"): 
    print("Game directory given is not root directory. Pass The directory in which gameinfo.txt is found")
    sys.exit(1)
if not os.path.exists(args.file): 
    print("-f vmf file given does not exist.")
    sys.exit(1)
    



def main(filename, gamedir, bCompilePal):
    print("Starting DynEnter precompile.")

    #base vmf name
    basename = os.path.basename(filename).split('.')[0].split('_')[1]

    #copy and mutate vmf
    vmf_outpath = os.path.dirname(os.path.realpath(sys.argv[0])) + '/vmfoutput'
    vmf_out = vmf_outpath + '/' + os.path.basename(filename)    
    
    #vscript paths
    vscriptpath = gamedir + '/scripts/vscripts' + '/dynenter/'
    vscriptout_p = vscriptpath + basename
    vscriptout_relativep = 'dynenter/' + basename
  
    
    #create vscript output dir, if not exist
    if not os.path.isdir(vscriptpath): 
        os.mkdir(vscriptpath)
        
    #create vscript output dir, if not exist
    if not os.path.isdir(vscriptout_p): 
        os.mkdir(vscriptout_p)
    
    #create map output dir, if not exist
    if not os.path.isdir(vmf_outpath): 
        os.mkdir(vmf_outpath)



    print("Finished generating output directories")
    
    #copy input vmf into string variable to remove dynamic-spawnified entities.    
    infile = open(filename, 'r')
    vmfstr = infile.read()
    infile.close()
    
    print("Parsing vmf..")
    #Dysphie magic vmf parser lol
    LBRACE, RBRACE = map(Suppress, '{}')
    key = dblQuotedString | Word(printables, excludeChars='{}/')
    value = Forward()
    node = Group(key + value)
    dblQuotedString.setParseAction(removeQuotes)
    section = Group(LBRACE + ZeroOrMore(node) + RBRACE)
    value << (key | section)
    results = OneOrMore(node).parseFile(filename).asList()
    
    outstr = ''
    count=0
    
    print("Analyzing cordon areas..")

    #get cordons
    for entry in results:
        if entry[0] == 'cordons':
            if not index_cordons(entry[1]):
                print("Could not find correctly named cordons." )
                print("To use dynamic entities: prefix your cordon with \'" + cordonprefix + "\'")
                print("Exiting..")
                return
    
    cordoncount = len(area_info)
    for i in range(cordoncount):
        str_areafuncs.append("local e = null \n\n")    #initialize string list

    print("Analyzing entities within areas..")

    #get entities 
    for entry in results:
        c_id = test_entity(entry[1])    #test if valid entity to dynamically spawn, and within a cordon
        if entry[0] == 'entity' and c_id >= 0:  
            count+=1
            
            area_info[c_id][AreaInfo.area_entcount] += 1
            #adding function wrap around each entity, so they can be spawned in iteratively, with delay
            str_areafuncs[c_id] += f'function EntSp_{area_info[c_id][AreaInfo.name]}{area_info[c_id][AreaInfo.area_entcount]}(){{'
            str_areafuncs[c_id] += stringify_entity(entry[1])
            str_areafuncs[c_id] += "}\n\n"
            
            #infodecal entities must precache their assets before creation
            #only infodecals use the "texture" keyvalue, so we can directly search for this
            for kv in entry[1]:
                if kv[0] == 'texture':
                    if kv[1] in must_precache_mat:
                        continue
                    else:
                        must_precache_mat.append(kv[1])
            
            #find id
            id=getid(entry[1])
            print("Removing entity id:" + str(id))
            #remove the entity from the input vmf
            vmfstr = remove_entity_file(id, vmfstr)
              
    
    out = open(vmf_out, 'w')
    out.write(vmfstr)
    
    #Generate area entity creation function.
    for c_id in range(cordoncount):
       
        logicscriptname = "DynEnter" + area_info[c_id][AreaInfo.name]
       #create logic script initialization
        str_areafuncs[c_id] += f'\
\n\
\nfunction SpawnEnts_{area_info[c_id][AreaInfo.name]}()\
\n{{\
\n\tprintl("Initializing area {area_info[c_id][AreaInfo.name]} entity spawn..")\n'
        
        ls_str = ""
        #the bulk of function calls    
        for i in range(area_info[c_id][AreaInfo.area_entcount]):
            delay = round(i/10.0, 2)
            index = i+1
            ls_str += f'\tEntFireByHandle(self, "RunScriptCode", "EntSp_{area_info[c_id][AreaInfo.name]}{index}()", {delay}, self, self)\n'
        #close brackets
        str_areafuncs[c_id] += ls_str + '}'


        #parse classname types
        classnamescount = len(classnames)
        str_areafuncs[c_id] += '\n\nlocal classnames = [ '
        for index, classname in enumerate(classnames):
            if index != classnamescount-1:
                str_areafuncs[c_id] += f'"{classname}",\n'
            else:
                str_areafuncs[c_id] += f'"{classname}"]\n\n'
            #str_areafuncs[c_id] += cnamesstr


        #Generate area entity destruction function. Premake destruction functions for each cordoned area
        str_areafuncs[c_id] += f'\
\nfunction DestroyEnts_{area_info[c_id][AreaInfo.name]}(){{     //remove cordoned entities\
\n\tforeach (classname in classnames){{\
\n\t\tlocal ent = null \
\n\t\twhile ( ( ent = Entities.FindByClassnameWithinBox(ent, classname, {area_info[c_id][1]}, {area_info[c_id][2]} ) ) != null ){{\
\n\t\t\tent.AcceptInput("Kill", "", self, self)\
\n\t\t\t}}\
\n\t\t}}\
\n}}'
        
    
    #make combined script, to be used on a logic script acting as an area manager
    overlord_scriptstr =  ""
    for cordon_info in area_info:
        overlord_scriptstr += f'DoIncludeScript("{vscriptout_relativep}/{cordon_info[AreaInfo.name]}.nut", null)\n'
    overlord_scriptstr += "/*\tincludes these functions from includescripts:"
    for cordon_info in area_info:   
        overlord_scriptstr += f'\tStartAreaSpawn_{cordon_info[AreaInfo.name]}()\n'
    for index, cordon_info in enumerate(area_info):   
        overlord_scriptstr += f'\tDestroyEnts_{cordon_info[AreaInfo.name]}()\n'
        if (index == len(area_info)-1):
            overlord_scriptstr += "*/"
        
    
    #write compiled vscript functions to files.
    #TODO cap cordons as this has infinite filewrite possibility
    
    #file combining all compiled vscript functions into one place
    out_ol = open(f'{vscriptout_p}/DynEnter_Overlord.nut', 'w')
    out_ol.write(overlord_scriptstr)
    #individual area scriptfiles:
    for index, cordon_info in enumerate(area_info):
        out = open(f'{vscriptout_p}/{cordon_info[AreaInfo.name]}.nut', 'w')
        out.write(str_areafuncs[index])
    
    #write precache things to precache file (wip)
    precacheout = open(f'{vscriptout_p}/precache.nut', 'w')
    for texture in must_precache_mat:
        precacheout.write( f'PrecacheMaterial("{texture}")\n' )

    
    #time to show results
    print(f'Found {count} entities in {cordoncount} cordons:')
    for i in range(cordoncount):
        print( area_info[i][AreaInfo.name] + ": " + str(area_info[i][AreaInfo.area_entcount]))
    for index, count in enumerate(entfound_count):
        print(f'{classnames[index]}: {count}')
    
    if bCompilePal:
        print(f'COMPILE_PAL_SET file "{vmf_out}"')




















def remove_entity_file(id, vmfstr):
    r = re.compile('entity\n{\n\t"id" "'+ str(id) +'".*?}\n}', re.DOTALL)
    return r.sub('', vmfstr)

#return entity id
def getid(entity_data):
    for kv in entity_data:
        if isinstance(kv[1], str):
            if kv[0] == 'id':
                return kv[1]


#evaluate if point lies within x y z min/max points
def is_inside_cordon(point, boxMins, boxMax):
    
    if boxMins[0] >= point[0] or point[0] >= boxMax[0] or        boxMins[1] >= point[1] or point[1] >= boxMax[1] or        boxMins[2] >= point[2] or point[2] >= boxMax[2]:
        return False
    else:    
        return True
    
    
#return cordon id in cordon_info list if entity in cordon, -1 if not found
def is_inside_cordons(point):

    for index, cordon_info in enumerate(area_info):
        if is_inside_cordon(point, cordon_info[1], cordon_info[2]):
            return index
    return -1


#   return the cordon index the entity is in, or -1 if not found
def test_entity(entity_data):
    
    for kv in entity_data:
        if kv[0] == 'classname':
            if kv[1] == '' or not kv[1] in classnames:
                return -1

        if isinstance(kv[1], str):
            if kv[0] == 'origin':
                return is_inside_cordons(list(map(float, kv[1].split())))
            
        if cfg_skip_named_ents == True and kv[0] == 'targetname':
            if kv[1] != '':
                return -1
            
        if not isinstance(kv[1], str) and kv[0] == 'solid':    # no solids
            return -1


def stringify_entity(entity_data):
    tierkv = ''
    tierconn = ''
    classname = ''
    bInfoDecal = False
    for kv in entity_data:
        if kv[0] == 'classname':
            classname = kv[1]
            entfound_count[classnames.index(classname)] += 1    #count classname occurances cause stats are great
            
        # if kv[0] == 'texture':  #mark as infodecal
        #     bInfoDecal = True
            
    entsp_info = []
    for kv in entity_data:
        
        if isinstance(kv[1], str):
            if kv[0] != 'id' and kv[0] != 'classname':
                entsp_info.append(f'\t{kv[0]} = "{kv[1]}"')
        elif kv[0] == 'connections':
            for conn in kv[1]:
                #in csgo, these are delimited by an escape character U+001b, for some reason
                # TODO: parse game name and change delimiter based on that
                params = conn[1].split(',')
                if len(params) != 5:
                    params = conn[1].split('')
                tierconn += f'e.AddOutput("{conn[0]}", "{params[0]}", "{params[1]}", "{params[2]}", {params[3]}, {params[4]})\n'


    outstr = f'\ne = SpawnEntityFromTable("{classname}",\n{{\n'
    item_len = len(entsp_info)-1
    for index, item in enumerate(entsp_info):
        outstr += item
        if index != item_len:
            outstr += ",\n"
        else :
            outstr += "\n});\n"
    # if bInfoDecal:
    #     outstr      += '\ne.AcceptInput("Activate", "", null, null)\n'
        
    if len(tierconn):
        outstr += tierconn

    return outstr




#   return: true if cordons with correct names found
def index_cordons(cordons_table):
    for cordon in cordons_table:
        if cordon[0] == 'cordon':
                        
            name    = ''
            pointList  = []
            for kv in cordon[1]:
                if kv[0] == 'name' and cordonprefix in kv[1]:
                    name = kv[1].split('_')[1]
                    
            if not name:
                continue
            
            
            
            for kv in cordon[1]:
                if kv[0] == 'box':
                    char_to_replace = {'(' : '', ')' : '' }
                    
                    pointMin = kv[1][0][1]
                    pointMax = kv[1][1][1]
                    
                    for key, value in char_to_replace.items():
                        pointMin = pointMin.replace(key, value)
                        pointMax = pointMax.replace(key, value)
                        
                    pointList.append(pointMin.split())
                    pointList.append(pointMax.split())
            

            area_info.append( [name, [float(pointList[0][0]), float(pointList[0][1]), float(pointList[0][2])], [float(pointList[1][0]), float(pointList[1][1]), float(pointList[1][2])], 0 ] )
            
    if len(area_info):
        return True
    else:
        return False
            
    # for cordon in area_info:
    #     print(cordon)
            






if __name__ == '__main__':
    main(args.file, args.game, args.p)

        
    
    


