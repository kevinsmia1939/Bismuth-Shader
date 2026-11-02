-- Luanti
-- SPDX-License-Identifier: LGPL-2.1-or-later
-- All changes are confined to the runner's disposable world copy.
local world=core.get_worldpath()
local game=graphics_test_game
local pose, player, scenes
local function event(kind,data)
 data=data or {};data.event=kind;data.time_us=core.get_us_time()
 core.log("action","Graphics benchmark: "..core.write_json(data,false))
end
local function read_json(path)
 local file=assert(io.open(path,"r"));local data=file:read("*a");file:close()
 return assert(core.parse_json(data))
end
local function write_json(path,data)
 local file=assert(io.open(path,"w"));file:write(core.write_json(data,true));file:close()
end
local function air(p) return core.get_node(p).name=="air" end
local function emerge(center,radius,lo,hi,done)
 core.emerge_area({x=center.x-radius,y=lo,z=center.z-radius},
  {x=center.x+radius,y=hi,z=center.z+radius},function(_,_,remaining)
   if remaining==0 then core.after(0,done) end
  end)
end
local function order(points,center)
 table.sort(points,function(a,b)
  local da=(a.x-center.x)^2+(a.z-center.z)^2
  local db=(b.x-center.x)^2+(b.z-center.z)^2
  if da~=db then return da<db end
  if a.x~=b.x then return a.x<b.x end
  if a.z~=b.z then return a.z<b.z end
  return a.y>b.y
 end)
end
local function scene(id,pos,yaw,pitch,time,evidence)
 return {id=id,pos=pos,yaw=yaw,pitch=pitch,timeofday=time,evidence=evidence}
end
local function prepare()
 scenes={}
 local forest_center
 for radius=0,4096,128 do
  for x=-radius,radius,128 do for z=-radius,radius,128 do
   if math.max(math.abs(x),math.abs(z))==radius then
    local data=core.get_biome_data({x=x,y=20,z=z})
    local name=data and core.get_biome_name(data.biome) or ""
    if game.forests[name] then
     forest_center={x=x,z=z};break
    end
   end
  end;if forest_center then break end end
  if forest_center then break end
 end
 assert(forest_center,"No forest biome candidate within 4096 nodes")
 event("prepare_forest",forest_center)
 emerge(forest_center,80,-32,128,function()
  local c=forest_center
  local leaves=core.find_nodes_in_area({x=c.x-64,y=0,z=c.z-64},{x=c.x+64,y=128,z=c.z+64},{"group:leaves"})
  assert(#leaves>=64,"Forest candidate lacks generated foliage")
  local ground=core.find_nodes_in_area_under_air({x=c.x-48,y=1,z=c.z-48},
   {x=c.x+48,y=100,z=c.z+48},game.forest_floors)
  order(ground,c)
  local floor
  for _,p in ipairs(ground) do
   if air(vector.add(p,{x=0,y=2,z=0})) and air(vector.add(p,{x=0,y=3,z=0})) then floor=p;break end
  end
  assert(floor,"No clear forest camera pose")
  order(leaves,floor)
  local target=leaves[math.min(80,#leaves)]
  local yaw=math.atan2(-(target.x-floor.x),target.z-floor.z)
  scenes[1]=scene("forest",vector.add(floor,{x=0,y=1,z=0}),yaw,0.08,0.5,
   {biome=core.get_biome_name(core.get_biome_data(floor).biome),leaves=#leaves,floor=core.get_node(floor).name})
  -- Valleys uses distinct river water; v7 carves river channels with ordinary
  -- water. Identify v7 channels with its actual noise and require nearby banks.
  local ridge_params=core.get_mapgen_setting_noiseparams("mgv7_np_ridge_uwater")
  local ridge=ridge_params and core.get_perlin(ridge_params)
  local candidates={c}
  for radius=256,2048,256 do
   for _,d in ipairs({{1,0},{0,1},{-1,0},{0,-1}}) do
    candidates[#candidates+1]={x=c.x+d[1]*radius,z=c.z+d[2]*radius}
   end
  end
  local function river(index)
   local center=assert(candidates[index],"No deep native river found")
   event("prepare_river",{index=index,x=center.x,z=center.z})
   emerge(center,112,-24,32,function()
    local water=core.find_nodes_in_area_under_air({x=center.x-104,y=-4,z=center.z-104},
     {x=center.x+104,y=8,z=center.z+104},game.waters)
    order(water,center)
    local selected
    for _,p in ipairs(water) do
     local name=core.get_node(p).name
     local channel=name==game.river or
      (ridge and math.abs(ridge:get_2d({x=p.x,y=p.z}))<=0.1)
     local deep=channel
     for dy=1,5 do
      deep=deep and core.get_node({x=p.x,y=p.y-dy,z=p.z}).name==name
     end
     local banked=false
     if deep then
      for _,axis in ipairs({"x","z"}) do
       local banks=0
       for _,sign in ipairs({-1,1}) do
        for distance=1,32 do
         local bank=vector.new(p);bank[axis]=bank[axis]+sign*distance
         local def=core.registered_nodes[core.get_node(bank).name]
         if def and def.walkable then banks=banks+1;break end
        end
       end
       if banks==2 then banked=true end
      end
     end
     if deep and banked then selected=p;break end
    end
    if not selected then river(index+1);return end
    local p=selected
    scenes[2]=scene("sunset_river",{x=p.x,y=p.y+5,z=p.z-10},0,0.5,0.78,
     {water=core.get_node(p).name,surface=p,channel_noise=ridge and ridge:get_2d({x=p.x,y=p.z}),banks_within=32})
    scenes[4]=scene("underwater",{x=p.x,y=p.y-4,z=p.z},0,0.12,0.5,
     {water=core.get_node(p).name,depth=5,surface=p})
    event("prepare_cave",c)
    emerge(c,80,-112,0,function()
     local floors=core.find_nodes_in_area_under_air({x=c.x-64,y=-96,z=c.z-64},
      {x=c.x+64,y=-12,z=c.z+64},{"group:stone"})
     order(floors,c)
     local best,best_run,best_d
     for _,f in ipairs(floors) do
      if air(vector.add(f,{x=0,y=2,z=0})) and air(vector.add(f,{x=0,y=3,z=0})) then
       for _,d in ipairs({{x=1,z=0},{x=0,z=1},{x=-1,z=0},{x=0,z=-1}}) do
        local run=0
        for n=1,16 do
         if not air({x=f.x+d.x*n,y=f.y+2,z=f.z+d.z*n}) then break end
         run=n
        end
        if run>(best_run or 0) then best,best_run,best_d=f,run,d end
       end
      end
      if (best_run or 0)>=12 then break end
     end
     assert(best and best_run>=6,"No open natural underground chamber found")
     local lamp={x=best.x+best_d.x*3,y=best.y+1,z=best.z+best_d.z*3}
     assert(air(lamp),"Cave lamp pose must be air")
     core.set_node(lamp,{name=game.lamp})
     scenes[3]=scene("glowing_cave",vector.add(best,{x=0,y=1,z=0}),
      math.atan2(-best_d.x,best_d.z),0,0,
      {floor=core.get_node(best).name,open_distance=best_run,lamp=lamp,lamp_name=game.lamp})
     local index=1
     local function preload()
      if index>#scenes then
       local manifest={version=1,game=game.id,seed=core.get_mapgen_setting("seed"),scenes=scenes}
       write_json(world.."/graphics-scenes.json",manifest)
       event("prepared",manifest)
       core.request_shutdown("Graphics scene preparation complete",false,0);return
      end
      local item=scenes[index];index=index+1
      emerge(item.pos,128,item.pos.y-64,item.pos.y+96,preload)
     end
     preload()
    end)
   end)
  end
  river(1)
 end)
end

local current,phase,deadline=0,"ready",0
local corrections=0
local warmup=tonumber(core.settings:get("graphics_benchmark_warmup")) or 20
local duration=tonumber(core.settings:get("graphics_benchmark_duration")) or 20
local function next_scene()
 current=current+1
 if current>#scenes then
  event("complete");core.request_shutdown("Graphics benchmark complete",false,0);phase="done";return
 end
 local item=scenes[current]
 pose=item.pos
 core.load_area(vector.subtract(pose,16),vector.add(pose,16))
 local eye=vector.add(pose,{x=0,y=player:get_properties().eye_height or 1.625,z=0})
 local head=core.get_node(eye)
 local head_def=assert(core.registered_nodes[head.name],"Unknown camera node")
 if item.id=="underwater" then
  assert(core.get_item_group(head.name,"water")>0,"Underwater camera must actually be submerged")
 else
  assert(not head_def.walkable and head_def.liquidtype=="none","Camera is inside solid or liquid geometry")
 end
 if item.id=="sunset_river" then
  assert(item.timeofday>=0.72 and item.timeofday<=0.85,"Sunset scene must use evening time")
  local target=vector.add(item.evidence.surface,{x=0,y=0.6,z=0})
  assert(not core.raycast(eye,target,false,false):next(),"River surface must be visible from the camera")
 end
 if item.id=="forest" then assert(item.evidence.biome:lower():find("forest"),"Forest biome evidence required") end
 player:set_pos(pose);player:set_look_horizontal(item.yaw);player:set_look_vertical(item.pitch)
 player:set_fov(70,false,0)
 player:set_sun({visible=true});player:set_moon({visible=true})
 player:set_clouds({density=0.4,height=120,thickness=16,speed={x=0,y=0}})
 player:set_lighting({shadows={intensity=0.65},volumetric_light={strength=0.15}})
 core.set_timeofday(item.timeofday)
 assert(player:set_wielded_item(item.id=="glowing_cave" and game.torch or ""))
 event("settle",item)
 phase="settle";deadline=core.get_us_time()+warmup*1000000
end
core.register_on_joinplayer(function(joined)
 player=joined
 game.freeze_environment()
 event("environment",{mob_spawning=false,weather_cycle=false,game=game.id})
 -- Remove persistent actors from this disposable copy as well as disabling
 -- new spawns in the runner config. Otherwise each profile sees different AI.
 player:set_physics_override({gravity=0,speed=0,liquid_sink=0})
 player:hud_set_flags({hotbar=false,healthbar=false,crosshair=false,wielditem=false,breathbar=false})
 if core.settings:get_bool("graphics_benchmark_prepare",false) then
  phase="prepare";core.after(1,prepare)
 else
  scenes=read_json(world.."/graphics-scenes.json").scenes
 end
end)
core.register_globalstep(function()
 if not player then return end
 -- Stable physics holds the pose. Repeated set_pos packets would invalidate
 -- temporal histories and flood the log during an otherwise static benchmark.
 if pose and vector.distance(player:get_pos(),pose)>0.02 then
  if phase=="measure" then corrections=corrections+1 end
  player:set_pos(pose)
 end
 local now=core.get_us_time()
 if phase=="ready" then
  local file=io.open(world.."/graphics-client-ready","r")
  if file then file:close();next_scene() end
 elseif phase=="settle" and now>=deadline then
  corrections=0
  event("measure_begin",{scene=scenes[current].id})
  phase="measure";deadline=now+duration*1000000
 elseif phase=="measure" and now>=deadline then
  event("measure_end",{scene=scenes[current].id,pose_corrections=corrections})
  next_scene()
 end
end)
