-- Luanti
-- SPDX-License-Identifier: LGPL-2.1-or-later
core.register_entity("volumetric_clouds_test:receiver",{
 initial_properties={visual="cube",textures={"default_stone.png","default_stone.png","default_stone.png","default_stone.png","default_stone.png","default_stone.png"},physical=false,pointable=false},
})
core.register_on_joinplayer(function(player)
 core.emerge_area({x=-16,y=-8,z=-16},{x=16,y=32,z=16},function(_,_,remaining)
  if remaining~=0 then return end
  core.after(0,function()
   local vm=VoxelManip()
   local minp,maxp=vm:read_from_map({x=-16,y=-8,z=-16},{x=16,y=32,z=16})
   local area=VoxelArea:new({MinEdge=minp,MaxEdge=maxp})
   local data=vm:get_data()
   local air,stone=core.get_content_id("air"),core.get_content_id("basenodes:stone")
   for z=-16,16 do for y=-8,32 do for x=-16,16 do
    local pillar=math.abs(x)<=1 and z>=10 and z<=11 and y<=24
    data[area:index(x,y,z)]=(y<=0 or pillar) and stone or air
   end end end
   vm:set_data(data);vm:write_to_map()
   player:set_physics_override({gravity=0,speed=0})
   player:set_pos({x=0,y=2,z=-6});player:set_look_horizontal(0);player:set_look_vertical(-0.3)
   core.add_entity({x=4,y=4,z=6},"volumetric_clouds_test:receiver")
   core.set_timeofday(0.32)
   player:set_lighting({shadows={intensity=0.65},volumetric_light={strength=0.15}})
   player:set_clouds({density=0.7,height=8,thickness=8,speed={x=2,y=-1}})
   core.log("action","Cloud integration: below layer")
   core.after(3,function() player:set_clouds({density=0});core.log("action","Cloud integration: clear") end)
   core.after(4,function() player:set_clouds({density=0.7}) end)
   core.after(5,function() player:set_clouds({thickness=0});core.log("action","Cloud integration: flat fallback") end)
   core.after(6,function() player:set_clouds({thickness=8}) end)
   core.after(7,function() player:set_sky({clouds=false});core.log("action","Cloud integration: hidden sky") end)
   core.after(8,function() player:set_sky({clouds=true}) end)
   core.after(9,function() player:set_pos({x=0,y=10,z=-6});core.log("action","Cloud integration: inside layer") end)
   core.after(11,function()
    player:set_pos({x=0,y=20,z=-6});player:set_look_vertical(0.3)
    core.log("action","Cloud integration: above layer")
   end)
   core.after(13,function()
    player:set_pos({x=0,y=2,z=-6});player:set_look_vertical(-0.3);player:set_fov(70,false,0.2)
   end)
   core.after(15,function() core.request_shutdown("Cloud integration done",false,0) end)
  end)
 end)
end)
