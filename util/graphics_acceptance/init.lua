-- Luanti
-- SPDX-License-Identifier: LGPL-2.1-or-later
-- All edits are in a disposable copy of the frozen benchmark world.
local world=core.get_worldpath()
local game=graphics_test_game
local function event(kind,data)
 data=data or {};data.event=kind;data.time_us=core.get_us_time()
 core.log("action","Graphics acceptance: "..core.write_json(data,false))
end
local player,scenes,stages,index,phase,begin
local duration=6
local surface_origin
local function prepare_surface(stage)
 local o=surface_origin
 local closed=stage.closed or false
 for x=-9,9 do for z=-9,9 do
  core.set_node({x=o.x+x,y=o.y,z=o.z+z},{name=x<0 and "default:sand" or "default:snowblock"})
  core.set_node({x=o.x+x,y=o.y+9,z=o.z+z},{name=closed and "default:stone" or "air"})
 end end
 for y=1,8 do for a=-9,9 do
  for _,p in ipairs({{x=o.x-9,y=o.y+y,z=o.z+a},{x=o.x+9,y=o.y+y,z=o.z+a},
   {x=o.x+a,y=o.y+y,z=o.z-9},{x=o.x+a,y=o.y+y,z=o.z+9}}) do
   core.set_node(p,{name=closed and "default:stone" or "air"})
  end
 end end
 for _,x in ipairs({-3,3}) do for z=1,5,2 do
  core.set_node({x=o.x+x,y=o.y+1,z=o.z+z},{name="default:grass_5"})
  core.set_node({x=o.x+x,y=o.y+2,z=o.z+z},{name="default:leaves",param2=1})
 end end
 core.set_node({x=o.x+1,y=o.y+1,z=o.z},{name=stage.placed and game.lamp or "air"})
end
local function position(stage,t)
 local s=scenes[stage.scene]
 local p=vector.new(s.pos)
 if stage.mode=="walk" then p.x=p.x+math.sin(t*math.pi*2)*0.5 end
 if stage.mode=="held_move" then
  -- Follow the scouted open cave corridor, which may face any cardinal axis.
  -- A fixed world-X move can put the native camera/lamp inside a side wall.
  p.x=p.x-math.sin(s.yaw)*t*1.5
  p.z=p.z+math.cos(s.yaw)*t*1.5
 end
 if stage.mode=="entry" or stage.mode=="exit" then
  local surface=scenes.sunset_river.evidence.surface
  p.x=surface.x;p.z=surface.z
  local a,b=surface.y+3,scenes.underwater.pos.y
  if stage.mode=="exit" then a,b=b,a end
  p.y=a+(b-a)*t
 end
 return p
end
local function apply(stage,t)
 local s=scenes[stage.scene]
 player:set_pos(position(stage,t))
 -- Cross the shadow-frustum's 15-degree recapture threshold in both directions.
 player:set_look_horizontal(s.yaw+(stage.mode=="walk" and 0.4*math.sin(t*math.pi*2) or 0))
 player:set_look_vertical(s.pitch)
 local time=stage.mode=="sunset" and 0.70+t*0.16 or s.timeofday
 if stage.mode=="grazing" then time=0.21+t*0.05 end
 core.set_timeofday(time)
end
local function next_stage()
 index=index+1
 local stage=stages[index]
 if not stage then
  if surface_origin then
   -- Preserve an open, unlit native-material patch for matched performance
   -- runs after the completed dark/removal measurements.
   prepare_surface({})
   local file=assert(io.open(world.."/graphics-surface-scene.json","w"))
   local scene=table.copy(scenes.surface)
   scene.id="surface_materials";scene.evidence={sand="default:sand",snow="default:snowblock",
    grass="default:grass_5",leaves="default:leaves",origin=surface_origin}
   file:write(core.write_json(scene,true));file:close()
  end
  event("complete")
  core.request_shutdown("Graphics acceptance complete",false,0)
  phase="done";return
 end
 local s=scenes[stage.scene]
 core.load_area(vector.subtract(s.pos,96),vector.add(s.pos,96))
 local lamp=scenes.glowing_cave.evidence.lamp
 core.load_area(vector.subtract(lamp,16),vector.add(lamp,16))
 core.set_node(lamp,{name=stage.placed and stage.scene~="surface" and game.lamp or "air"})
 if stage.scene=="surface" then prepare_surface(stage) end
 assert(player:set_wielded_item(stage.held and game.torch or ""))
 player:set_sun({visible=true});player:set_moon({visible=true})
 player:set_clouds({density=0.4,height=120,thickness=16,speed={x=0,y=0}})
 player:set_lighting({shadows={intensity=0.65},volumetric_light={strength=0.15}})
 if core.settings:get_bool("graphics_acceptance_surface_materials",false) then
  -- The game's default min=max fixes exposure. Use an authored adaptive range
  -- here, with its fast default rates, to exercise the client's rate limits.
  player:set_lighting({exposure={luminance_min=-6,luminance_max=0,
   speed_dark_bright=1000,speed_bright_dark=1000},bloom={intensity=0.05,
    strength_factor=stage.id=="surface_grazing" and 0 or 1}})
 end
 if stage.scene=="glowing_cave" and core.settings:get_bool("graphics_acceptance_bright_cave",false) then
  -- Model looking into the cave from daylight: retain a bright outdoor sky
  -- and fog color even though the receiver's native skylight is zero.
  player:set_sky({type="plain",base_color="#99CCFF",auto_dim_skybox=false,
   fog={fog_color="#99CCFF"}})
  core.log("action","Graphics acceptance: bright daylight sky over unlit cave")
 end
 apply(stage,0)
 event("prepare",{id=stage.id,index=index,scene=stage.scene,placed=stage.placed or false,held=stage.held or false})
 phase="wait"
end
core.register_on_joinplayer(function(joined)
 player=joined
 game.freeze_environment()
 player:set_physics_override({gravity=0,speed=0,liquid_sink=0})
 player:hud_set_flags({hotbar=false,healthbar=false,crosshair=false,wielditem=false,breathbar=false})
 local file=assert(io.open(world.."/graphics-scenes.json","r"))
 local manifest=assert(core.parse_json(file:read("*a")));file:close()
 scenes={};for _,scene in ipairs(manifest.scenes) do scenes[scene.id]=scene end
 stages={
  {id="forest_movement",scene="forest",mode="walk"},
  {id="sunset_transition",scene="forest",mode="sunset"},
  {id="river_reflections",scene="sunset_river",mode="walk"},
  {id="water_entry",scene="sunset_river",mode="entry"},
  {id="underwater_lamp",scene="underwater",held=true},
  {id="water_exit",scene="sunset_river",mode="exit"},
  {id="cave_dark",scene="glowing_cave"},
  {id="cave_placed",scene="glowing_cave",placed=true},
  {id="cave_removed",scene="glowing_cave"},
  {id="held_movement",scene="glowing_cave",held=true,mode="held_move"},
  {id="held_removed",scene="glowing_cave"},
 }
 if core.settings:get_bool("graphics_acceptance_surface_materials",false) then
  assert(game.id=="minetest","Surface-material fixtures require the primary Minetest Game target")
  for _,name in ipairs({"default:sand","default:snowblock","default:leaves","default:grass_5"}) do
   assert(core.registered_nodes[name],"Missing native surface material: "..name)
  end
  surface_origin=vector.round(vector.add(scenes.forest.pos,{x=0,y=30,z=0}))
  core.load_area(vector.subtract(surface_origin,32),vector.add(surface_origin,32))
  for x=-8,8 do for z=-8,8 do for y=1,8 do
   core.set_node(vector.add(surface_origin,{x=x,y=y,z=z}),{name="air"})
  end end end
  scenes.surface={pos=vector.add(surface_origin,{x=0,y=1,z=-6}),yaw=0,pitch=0.35,timeofday=0.5}
  for _,stage in ipairs({
   {id="surface_daylight",mode="walk"},
   {id="surface_grazing",mode="grazing"},
   {id="surface_dark",closed=true},
   {id="surface_placed",closed=true,placed=true},
   {id="surface_removed",closed=true},
   {id="surface_held",closed=true,held=true,mode="walk"},
   {id="surface_held_removed",closed=true},
  }) do stage.scene="surface";table.insert(stages,stage) end
  core.log("action","Graphics acceptance: native sand/snow/foliage fixtures with adaptive exposure")
 end
 index=0;phase="start"
end)
core.register_globalstep(function()
 if not player or phase=="done" then return end
 if phase=="start" then next_stage();return end
 local stage=stages[index]
 if phase=="wait" then
  local file=io.open(world.."/graphics-phase-"..index.."-ready","r")
  if file then
   file:close();begin=core.get_us_time();phase="exercise"
   event("begin",{id=stage.id,index=index})
  end
 elseif phase=="exercise" then
  local t=math.min((core.get_us_time()-begin)/(duration*1000000),1)
  apply(stage,t)
  if t>=1 then
   event("end",{id=stage.id,index=index,pos=player:get_pos(),timeofday=core.get_timeofday()})
   next_stage()
  end
 end
end)
