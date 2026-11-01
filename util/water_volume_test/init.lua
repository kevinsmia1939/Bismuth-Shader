-- Luanti
-- SPDX-License-Identifier: LGPL-2.1-or-later
core.register_node("water_volume_test:water", {
 drawtype="liquid", tiles={"default_water.png"},
 special_tiles={{name="default_water.png",backface_culling=false}},
 use_texture_alpha="blend", paramtype="light", waving=3,
 liquidtype="source", liquid_alternative_source="water_volume_test:water",
 liquid_alternative_flowing="water_volume_test:flow", liquid_range=8,
 walkable=false, pointable=false, diggable=false, buildable_to=true,
 sunlight_propagates=true, post_effect_color={a=80,r=15,g=65,b=110},
 post_effect_color_shaded=true,
})

for name,waving in pairs({flow=3,static_flow=0}) do
 core.register_node("water_volume_test:"..name,{
  drawtype="flowingliquid", tiles={"default_water.png"},
  special_tiles={{name="default_water.png",backface_culling=false},{name="default_water.png",backface_culling=false}},
  use_texture_alpha="blend",paramtype="light",paramtype2="flowingliquid",waving=waving,
  liquidtype="flowing",liquid_alternative_source="water_volume_test:water",
  liquid_alternative_flowing="water_volume_test:"..name,liquid_range=8,
  walkable=false,pointable=false,diggable=false,buildable_to=true,
  sunlight_propagates=true,post_effect_color={a=80,r=15,g=65,b=110},post_effect_color_shaded=true,
 })
end

core.register_on_joinplayer(function(player)
 player:set_physics_override({gravity=0,speed=0,liquid_sink=0})
 core.emerge_area({x=-12,y=-8,z=-12},{x=12,y=16,z=12},function(_,_,remaining)
  if remaining~=0 then return end
  core.after(0,function()
   local vm=VoxelManip()
   local minp,maxp=vm:read_from_map({x=-12,y=-8,z=-12},{x=12,y=16,z=12})
   local area=VoxelArea:new({MinEdge=minp,MaxEdge=maxp})
   local data=vm:get_data()
   local air,stone=core.get_content_id("air"),core.get_content_id("basenodes:stone")
   local water=core.get_content_id("water_volume_test:water")
   for z=-12,12 do for y=-8,16 do for x=-12,12 do
    local wall=(math.abs(x)==7 or math.abs(z)==7) and y<=4
    local pool=math.abs(x)<=6 and math.abs(z)<=6 and y>=0 and y<=4
    data[area:index(x,y,z)]=pool and water or ((y<0 or wall) and stone or air)
   end end end
   vm:set_data(data);vm:write_to_map()
   player:set_physics_override({gravity=0,speed=0,liquid_sink=0})
   player:set_pos({x=0,y=1,z=-2});player:set_look_horizontal(0);player:set_look_vertical(0.5)
   core.set_timeofday(0.5)
   player:set_lighting({shadows={intensity=0.65}})
   core.log("action","Water integration: submerged")
   core.after(3,function()
    for x=-7,7 do for z=-7,7 do core.set_node({x=x,y=7,z=z},{name="basenodes:stone"}) end end
    core.log("action","Water integration: roof")
   end)
   core.after(5,function()
    for x=-7,7 do for z=-7,7 do core.remove_node({x=x,y=7,z=z}) end end
   end)
   core.after(6,function()
    player:set_pos({x=0,y=8,z=-2});player:set_look_vertical(0.8)
    core.log("action","Water integration: above")
   end)
   core.after(8,function()
    player:set_pos({x=0,y=1,z=-2});player:set_look_vertical(0.5)
   end)
   core.after(9,function()
    for z=-3,0 do for y=1,4 do core.remove_node({x=7,y=y,z=z}) end end
    player:set_pos({x=6.5,y=1,z=-2})
    core.log("action","Water integration: shoreline")
   end)
   core.after(10,function()
    for x=-6,6 do for z=-6,6 do for y=0,4 do core.remove_node({x=x,y=y,z=z}) end end end
    -- The shoreline camera can leave one pool block outside the send frustum.
    -- Explicitly sync these four loaded blocks before checking the full drain.
    core.after(0.3,function()
     for x=-1,0 do for z=-1,0 do player:send_mapblock({x=x,y=0,z=z}) end end
    end)
    core.log("action","Water integration: drained")
   end)
   core.after(12,function()
    for x=-6,6 do for z=-6,6 do for y=0,4 do core.set_node({x=x,y=y,z=z},{name="water_volume_test:water"}) end end end
    player:set_pos({x=0,y=1,z=-2})
    player:set_fov(70,false,0.2)
    core.after(0.3,function()
     for x=-1,0 do for z=-1,0 do player:send_mapblock({x=x,y=0,z=z}) end end
    end)
    core.log("action","Water integration: restored")
   end)
   local held_eye_y,held_eye_x= nil,0
   core.register_globalstep(function()
    if held_eye_y and player:is_valid() then
     player:set_pos({x=held_eye_x,y=held_eye_y-player:get_properties().eye_height,z=-2})
    end
   end)
   local function wave_camera(eye_y, phase, eye_x)
    -- Keep both test poses inside the same native source node. Waving source
    -- vertices are strictly below the static 4.5-node surface with height=1.
    local eye_height=player:get_properties().eye_height
    held_eye_y=eye_y
    held_eye_x=eye_x or 0
    player:set_pos({x=held_eye_x,y=eye_y-eye_height,z=-2})
    core.log("action","Water integration: "..phase)
   end
   core.after(13,function() wave_camera(3.99,"wave submerged") end)
   core.after(14,function() wave_camera(4.495,"wave gap") end)
   core.after(15,function() wave_camera(3.99,"wave submerged again") end)
   local function flow_patch(name)
    for x=-2,2 do for z=-4,0 do
     core.set_node({x=x,y=4,z=z},{name="water_volume_test:"..name,param2=math.min(7,x+z+6)})
    end end
   end
   core.after(18,function()
    flow_patch("static_flow")
    wave_camera(4.02,"flow submerged",-0.25)
   end)
   -- At this X/Z the sloped rest surface is 4.03125; a flat level slab
   -- would incorrectly keep the 4.045 pose underwater.
   core.after(20,function() wave_camera(4.045,"flow slope gap",-0.25) end)
   core.after(22,function()
    flow_patch("flow")
    wave_camera(3.49,"waving flow submerged",-0.25)
   end)
   -- Waves always lower this surface; 4.025 is wet without displacement.
   core.after(24,function() wave_camera(4.025,"waving flow gap",-0.25) end)
   core.after(26,function() wave_camera(3.49,"waving flow submerged again",-0.25) end)
   core.after(19,function() core.log("action","Water integration: flow submerged held") end)
   core.after(21,function() core.log("action","Water integration: flow slope gap held") end)
   core.after(23,function() core.log("action","Water integration: waving flow submerged held") end)
   core.after(25,function() core.log("action","Water integration: waving flow gap held") end)
   core.after(27,function() core.log("action","Water integration: waving flow submerged again held") end)
   core.after(28,function() core.request_shutdown("Water volume integration done",false,0) end)
  end)
 end)
end)
