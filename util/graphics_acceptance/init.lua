-- Luanti
-- SPDX-License-Identifier: LGPL-2.1-or-later
-- All edits are in a disposable copy of the frozen benchmark world.
local world=core.get_worldpath()
local function event(kind,data)
 data=data or {};data.event=kind;data.time_us=core.get_us_time()
 core.log("action","Graphics acceptance: "..core.write_json(data,false))
end
local player,scenes,stages,index,phase,begin
local duration=6
local function position(stage,t)
 local s=scenes[stage.scene]
 local p=vector.new(s.pos)
 if stage.mode=="walk" then p.x=p.x+math.sin(t*math.pi*2)*0.5 end
 if stage.mode=="held_move" then p.x=p.x+t*1.5 end
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
 core.set_timeofday(stage.mode=="sunset" and 0.70+t*0.16 or s.timeofday)
end
local function next_stage()
 index=index+1
 local stage=stages[index]
 if not stage then
  event("complete")
  core.request_shutdown("Graphics acceptance complete",false,0)
  phase="done";return
 end
 local s=scenes[stage.scene]
 core.load_area(vector.subtract(s.pos,96),vector.add(s.pos,96))
 local lamp=scenes.glowing_cave.evidence.lamp
 core.load_area(vector.subtract(lamp,16),vector.add(lamp,16))
 core.set_node(lamp,{name=stage.placed and "mcl_nether:glowstone" or "air"})
 assert(player:set_wielded_item(stage.held and "mcl_torches:torch" or ""))
 player:set_sun({visible=true});player:set_moon({visible=true})
 player:set_clouds({density=0.4,height=120,thickness=16,speed={x=0,y=0}})
 player:set_lighting({shadows={intensity=0.65},volumetric_light={strength=0.15}})
 apply(stage,0)
 event("prepare",{id=stage.id,index=index,scene=stage.scene,placed=stage.placed or false,held=stage.held or false})
 phase="wait"
end
core.register_on_joinplayer(function(joined)
 player=joined
 for _,name in ipairs({"gamerule:doMobSpawning","gamerule:doWeatherCycle"}) do
  assert(vl_tuning.registered_settings[name]):set(false)
 end
 mcl_weather.change_weather("none");core.clear_objects({mode="full"})
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
