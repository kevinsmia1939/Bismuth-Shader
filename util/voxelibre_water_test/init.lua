-- Luanti
-- SPDX-License-Identifier: LGPL-2.1-or-later
-- Uses naturally generated water. Never places or removes terrain.
local pose
core.register_on_joinplayer(function(player)
 local regions={{0,0,112}}
 for _,radius in ipairs({160,320,640,1280}) do
  for _,direction in ipairs({{1,0},{-1,0},{0,1},{0,-1}}) do
   regions[#regions+1]={direction[1]*radius,direction[2]*radius,32}
  end
 end
 local function scout(index)
  local region=regions[index]
  if not region then error("Native water compatibility: no generated water column found") end
  local minp={x=region[1]-region[3],y=-16,z=region[2]-region[3]}
  local maxp={x=region[1]+region[3],y=8,z=region[2]+region[3]}
  core.emerge_area(minp,maxp,function(_,_,remaining)
   if remaining~=0 then return end
   core.after(0,function()
    local points=core.find_nodes_in_area(minp,maxp,{"group:water"})
    local selected
    for _,p in ipairs(points) do
     local name=core.get_node(p).name
     local def=core.registered_nodes[name]
     local column=def and def.liquidtype=="source"
     for dy=1,3 do
      local upper=core.registered_nodes[core.get_node(vector.add(p,{x=0,y=dy,z=0})).name]
      column=column and upper and upper.liquidtype=="source" and
       core.get_item_group(upper.name,"water")>0
     end
     if column and (not selected or p.y>selected.y) then
      selected=vector.new(p)
     end
    end
    if not selected then scout(index+1);return end
    pose=selected
    player:set_physics_override({gravity=0,speed=0})
    player:set_look_horizontal(0);player:set_look_vertical(0.4)
    player:set_lighting({shadows={intensity=0.65},volumetric_light={strength=0.15}})
    core.set_timeofday(0.5)
    if core.settings:get_bool("native_water_test_clouds",false) then
     player:set_clouds({density=0.7,height=16,thickness=8,speed={x=2,y=-1}})
    end
    local top=selected.y+3
    while top<128 and core.get_item_group(core.get_node({x=selected.x,y=top,z=selected.z}).name,"water")>0 do
     top=top+1
    end
    core.log("action","Native water compatibility: submerged "..core.get_node(pose).name)
    if core.settings:get_bool("native_water_test_dynamic_light",false) then
     local torch=assert(core.registered_nodes["mcl_torches:torch"])
     assert(torch.light_source>0)
     assert(player:set_wielded_item(""))
     core.after(3,function()
      assert(player:set_wielded_item("mcl_torches:torch"))
      core.log("action","Native dynamic lighting: held torch")
     end)
     core.after(8,function()
      assert(player:set_wielded_item(""))
      core.log("action","Native dynamic lighting: removed torch")
     end)
    end
    core.after(6,function()
     pose={x=selected.x,y=top+3,z=selected.z}
     core.log("action","Native water compatibility: above")
    end)
    core.after(9,function()
     pose=selected
     core.log("action","Native water compatibility: submerged again")
    end)
    core.after(14,function() core.request_shutdown("Native water compatibility complete",false,0) end)
   end)
  end)
 end
 core.after(2,function() scout(1) end)
end)
core.register_globalstep(function()
 if not pose then return end
 for _,player in ipairs(core.get_connected_players()) do player:set_pos(pose) end
end)
