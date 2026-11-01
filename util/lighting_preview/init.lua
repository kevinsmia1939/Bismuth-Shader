-- Luanti
-- SPDX-License-Identifier: LGPL-2.1-or-later
-- Fixed scene for visual comparison of water, atmosphere, materials and color bounce.
core.register_on_joinplayer(function(player)
 core.emerge_area({x=-32,y=-16,z=-32},{x=32,y=32,z=48},function(_,_,remaining)
  if remaining ~= 0 then return end
  core.after(0,function()
   local vm = VoxelManip()
   local emin,emax=vm:read_from_map({x=-28,y=-5,z=-28},{x=28,y=24,z=40})
   local area=VoxelArea:new({MinEdge=emin,MaxEdge=emax})
   local data=vm:get_data()
   local ids={}
   for _,name in ipairs({'air','basenodes:stone','basenodes:dirt_with_grass','basenodes:tree','basenodes:leaves','basenodes:desert_stone','basenodes:sand','basenodes:water_source'}) do ids[name]=core.get_content_id(name) end
   local function box(x1,y1,z1,x2,y2,z2,name)
    for z=z1,z2 do for y=y1,y2 do for x=x1,x2 do data[area:index(x,y,z)]=ids[name] end end end
   end
   box(-28,-5,-28,28,24,40,'air')
   box(-28,-4,-28,28,-1,40,'basenodes:stone')
   box(-28,0,-28,28,0,40,'basenodes:dirt_with_grass')
   box(-8,1,3,7,1,16,'basenodes:stone')
   box(-8,2,15,7,7,16,'basenodes:desert_stone')
   box(-8,2,3,-7,7,16,'basenodes:desert_stone')
   for _,x in ipairs({-6,-2,2,6}) do
    box(x,2,6,x,5,6,'basenodes:stone')
    box(x-1,6,5,x+1,6,7,'basenodes:stone')
   end
   for i=0,3 do box(2+i,1,1+i,6,1+i,4+i,'basenodes:stone') end
   for _,t in ipairs({{-13,5},{11,12},{-13,21},{14,23}}) do
    local x,z=t[1],t[2]
    box(x-2,5,z-2,x+2,7,z+2,'basenodes:leaves')
    box(x-1,8,z-1,x+1,8,z+1,'basenodes:leaves')
    box(x,1,z,x,5,z,'basenodes:tree')
   end
   box(10,0,-2,17,0,8,'basenodes:sand')
   box(11,0,-1,16,0,7,'basenodes:water_source')
   -- Broad foreground water reflects the architecture behind it.
   box(-7,0,-7,15,0,2,'basenodes:sand')
   box(-6,0,-6,14,0,1,'basenodes:water_source')
   vm:set_data(data); vm:write_to_map()
   core.set_timeofday(0.32)
   if core.settings:get_bool("enable_dynamic_shadows") then
    player:set_lighting({shadows={intensity=0.65},volumetric_light={strength=0.15}})
   end
   player:set_pos({x=9,y=2,z=-13})
   player:set_look_horizontal(0.36); player:set_look_vertical(0.10)
   player:set_clouds({density=0})
   player:set_physics_override({speed=0,gravity=0})
   player:hud_set_flags({hotbar=false,healthbar=false,crosshair=false,wielditem=false,breathbar=false,basic_debug=false,chat=false})
  end)
 end)
end)
local preview_time = 0
local preview_motion = core.settings:get_bool("lighting_preview_motion", false)
core.register_globalstep(function(dtime)
 preview_time = preview_time + dtime
 for _,player in ipairs(core.get_connected_players()) do
  local shift = preview_motion and math.sin(preview_time * 0.5) or 0
  player:set_pos({x=9+shift*3,y=2,z=-13})
  player:set_look_horizontal(0.36+shift*0.15)
  player:set_look_vertical(0.10)
 end
end)
