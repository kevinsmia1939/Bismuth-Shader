-- Luanti
-- SPDX-License-Identifier: LGPL-2.1-or-later
-- Runtime integration test: exact RGB emission, map updates, model binding, teardown.
for _,channel in ipairs({{"red", "#ff0000"}, {"green", "#00ff00"}, {"blue", "#0000ff"}}) do
 core.register_node("voxel_lighting_test:"..channel[1], {
  tiles={"default_stone.png"}, paramtype="light", light_source=14,
  light_source_color=channel[2], groups={cracky=1},
 })
end
core.register_node("voxel_lighting_test:inferred", {
 tiles={"default_stone.png"}, paramtype="light", light_source=14,
})
core.register_node("voxel_lighting_test:black", {
 tiles={"default_stone.png"}, paramtype="light", light_source=14,
 light_source_color="#000000",
})
for _,filter in ipairs({{"filter_green","#80ff80"},{"filter_blue","#8080ff"}}) do
 core.register_node("voxel_lighting_test:"..filter[1], {
  drawtype="glasslike", tiles={"default_stone.png^[opacity:64"}, use_texture_alpha="blend",
  paramtype="light", sunlight_propagates=true, light_transmission_color=filter[2],
 })
end
core.register_node("voxel_lighting_test:filter_inferred", {
 drawtype="glasslike", tiles={"default_stone.png^[opacity:64"}, use_texture_alpha="blend",
 paramtype="light", sunlight_propagates=true, color="#ff8080",
})
core.register_entity("voxel_lighting_test:receiver", {
 initial_properties={visual="cube", textures={"default_stone.png", "default_stone.png", "default_stone.png", "default_stone.png", "default_stone.png", "default_stone.png"}, physical=false, glow=0},
})
core.register_entity("voxel_lighting_test:moving_lamp", {
 initial_properties={visual="item", wield_item="voxel_lighting_test:blue 9", physical=false},
})
core.register_on_joinplayer(function(player)
 core.emerge_area({x=-16,y=-8,z=-16}, {x=16,y=16,z=16}, function(_,_,remaining)
  if remaining~=0 then return end
  core.after(0,function()
   local vm=VoxelManip()
   local minp,maxp=vm:read_from_map({x=-16,y=-8,z=-16},{x=16,y=16,z=16})
   local area=VoxelArea:new({MinEdge=minp,MaxEdge=maxp})
   local data=vm:get_data()
   local air=core.get_content_id("air")
   local stone=core.get_content_id("basenodes:stone")
   local water=core.get_content_id("basenodes:water_source")
   for z=-16,16 do for y=-8,16 do for x=-16,16 do
    local pool=x>=-6 and x<=6 and z>=0 and z<=12 and y>=-3 and y<=0
    data[area:index(x,y,z)]=pool and water or (y<=0 and stone or air)
   end end end
   vm:set_data(data);vm:write_to_map()
   -- Blue is behind the camera but in a loaded map block: no screen-space input.
   local lamps={{x=-4,y=2,z=3},{x=0,y=2,z=3},{x=4,y=2,z=-8}}
   for i,color in ipairs({"red","green","blue"}) do core.set_node(lamps[i],{name="voxel_lighting_test:"..color}) end
   if core.settings:get_bool("voxel_test_transmission",false) then
    local function filters(kind)
     for z=4,6 do core.set_node({x=3,y=2,z=z},{name=kind}) end
    end
    filters("voxel_lighting_test:filter_green")
    core.log("action","Transmission integration: green")
    core.after(4,function()
     filters("voxel_lighting_test:filter_blue")
     core.log("action","Transmission integration: blue")
    end)
    core.after(7,function()
     filters("voxel_lighting_test:filter_inferred")
     core.log("action","Transmission integration: inferred")
    end)
    core.after(10,function()
     filters("air")
     core.log("action","Transmission integration: removed")
    end)
    if core.settings:get_bool("voxel_test_dynamic_lighting",false) then
     core.after(18,function()
      filters("voxel_lighting_test:filter_green")
      core.log("action","Transmission integration: moving light filter")
     end)
     core.after(22,function() filters("air") end)
    end
   end
   core.add_entity({x=0,y=1,z=6},"voxel_lighting_test:receiver")
   if core.settings:get_bool("voxel_test_native_emission",false) then
    local sprite=core.add_entity({x=-3,y=2,z=2},"voxel_lighting_test:receiver")
    sprite:set_properties({visual="sprite"})
    for _,state in ipairs({{2,14,true,"glowing"},{7,0,true,"ordinary"},{9,0,false,"unshaded"}}) do
     core.after(state[1],function()
      sprite:set_properties({glow=state[2],shaded=state[3]})
      core.log("action","Native emission integration: sprite "..state[4])
     end)
    end
    local position={x=2,y=2,z=2}
    for _,state in ipairs({{1,"voxel_lighting_test:black","black emitter"},
                           {3,"basenodes:stone","ordinary replacement"},
                           {4,"voxel_lighting_test:black","restored emitter"},{5,"air","removed"}}) do
     core.after(state[1],function()
      core.set_node(position,{name=state[2]})
      core.log("action","Native emission integration: "..state[3])
     end)
    end
   end
   if core.settings:get_bool("voxel_test_emission_mask",false) then
    local glow=core.add_entity({x=3,y=2,z=3},"voxel_lighting_test:receiver")
    core.after(2,function()
     glow:set_properties({glow=14})
     core.log("action","Emission mask integration: object glowing")
    end)
    core.after(7,function()
     glow:set_properties({glow=0})
     core.log("action","Emission mask integration: object ordinary")
    end)
    core.after(9,function()
     glow:set_properties({shaded=false})
     core.log("action","Emission mask integration: object unshaded")
    end)
   end
   player:set_pos({x=0,y=2,z=-4});player:set_look_horizontal(0);player:set_look_vertical(0.25)
   player:set_physics_override({gravity=0,speed=0});core.set_timeofday(0)
   player:set_lighting({shadows={intensity=0.65},volumetric_light={strength=0.15}})
   if core.settings:get_bool("voxel_test_geometry",false) then
    local kinds={"basenodes:stone","voxel_lighting_test:filter_green","voxel_lighting_test:filter_blue","air"}
    for pulse=0,11 do
     local kind=kinds[pulse%4+1]
     core.after(17+pulse*0.3,function()
      for y=1,3 do for z=4,6 do core.set_node({x=2,y=y,z=z},{name=kind}) end end
      core.log("action","Geometry integration: "..kind)
     end)
    end
   end
   if core.settings:get_bool("voxel_test_cloud_gi",false) then
    player:set_lighting({shadows={intensity=0.65,direction={x=0,y=1,z=0}}})
    player:set_clouds({density=1,height=16,thickness=8,color="#ffffffff",speed={x=0,y=0}})
    core.log("action","Lighting integration: cloud GI overcast")
    core.after(5,function()
     player:set_clouds({density=0})
     core.log("action","Lighting integration: cloud GI clear")
    end)
    core.after(9,function()
     player:set_clouds({density=1})
     core.log("action","Lighting integration: cloud GI overcast restored")
    end)
   end
   core.after(6,function() core.remove_node(lamps[3]) end)
   if core.settings:get_bool("voxel_test_fog_denoising",false) then
    core.after(3,function()
     player:set_lighting({shadows={intensity=0.65,direction={x=0,y=0,z=0}}})
     player:set_sun({visible=false});player:set_moon({visible=false})
     core.log("action","Fog integration: hidden lights")
    end)
    core.after(5,function()
     player:set_sun({visible=true});player:set_moon({visible=true})
     core.log("action","Fog integration: restored lights")
    end)
   end
   core.after(10,function() core.remove_node(lamps[1]);core.remove_node(lamps[2]) end)
   core.after(8,function()
    core.set_timeofday(0.23);core.log("action","Lighting integration: low sun")
   end)
   core.after(10.5,function()
    core.set_timeofday(0.5);core.log("action","Lighting integration: noon")
   end)
   core.after(12,function()
    player:set_lighting({shadows={intensity=0.65,direction={x=0.4,y=1,z=0.2}},
     volumetric_light={strength=0.15}})
    player:set_fov(70,false,0.2)
    core.log("action","Lighting integration: custom direction")
   end)
   core.after(13,function()
    player:set_pos({x=0,y=-3,z=4})
    core.log("action","Fog integration: submerged")
   end)
   core.after(14,function()
    player:set_pos({x=0,y=2,z=-4});player:set_fov(0,false,0.2)
    core.log("action","Fog integration: above water")
   end)
   if core.settings:get_bool("voxel_test_dynamic_lighting",false) then
    local actor
    local function held_color(color)
     local item=ItemStack("voxel_lighting_test:inferred 9")
     item:get_meta():set_string("color",color)
     assert(player:set_wielded_item(item))
    end
    core.after(16,function()
     held_color("#ff0000")
     if core.settings:get_bool("voxel_test_water_lighting",false) then
      player:set_pos({x=0,y=-3,z=4})
      player:set_physics_override({liquid_sink=0})
      core.log("action","Water lighting integration: held underwater")
     end
     core.log("action","Dynamic lighting integration: held red")
    end)
    core.after(20,function()
     held_color("#00ff00")
     core.log("action","Dynamic lighting integration: held green")
    end)
    if core.settings:get_bool("voxel_test_water_lighting",false) then
     core.after(22,function()
      player:set_pos({x=0,y=2,z=-4})
      core.log("action","Water lighting integration: above after held")
     end)
    end
    core.after(24,function()
     assert(player:set_wielded_item(""))
     -- Behind the camera, with a fractional source location.
     actor=core.add_entity({x=-3.25,y=2,z=-8},"voxel_lighting_test:moving_lamp")
     core.log("action","Dynamic lighting integration: item blue")
    end)
    core.after(26,function()
     actor:set_properties({wield_item="",textures={"voxel_lighting_test:blue"}})
     core.log("action","Dynamic lighting integration: legacy item blue")
    end)
    core.after(27,function()
     actor:set_pos({x=4.25,y=2,z=4})
    end)
    core.after(28,function()
     actor:set_properties({visual="node",node={name="voxel_lighting_test:red"}})
     core.log("action","Dynamic lighting integration: moved node red")
    end)
    core.after(30,function()
     actor:set_properties({is_visible=false})
     core.log("action","Dynamic lighting integration: hidden")
    end)
    core.after(32,function()
     actor:set_properties({is_visible=true})
     core.log("action","Dynamic lighting integration: restored")
    end)
    core.after(34,function()
     actor:remove()
     core.log("action","Dynamic lighting integration: removed")
    end)
    core.after(36,function()
     assert(player:set_wielded_item("voxel_lighting_test:black"))
     core.log("action","Dynamic lighting integration: explicit black")
    end)
    core.after(40,function()
     assert(player:set_wielded_item(""))
     core.request_shutdown("Dynamic voxel integration test done",false,0)
    end)
   else
    core.after(15,function() core.request_shutdown("Voxel integration test done",false,0) end)
   end
  end)
 end)
end)
