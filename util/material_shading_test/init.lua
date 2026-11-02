-- Luanti
-- SPDX-License-Identifier: LGPL-2.1-or-later
local function register(name, tile, light)
 core.register_node("material_shading_test:"..name, {tiles={tile},groups={cracky=1},
  light_source=light or 0,light_source_color=light and "#ff8030" or nil})
end
register("rough",{name="material_test_base.png",normal_texture="material_test_normal.png",material_texture="material_test_rough.png"})
register("metal",{name="material_test_base.png",normal_texture="material_test_normal.png",material_texture="material_test_metal.png"})
register("emissive",{name="material_test_base.png",normal_texture="material_test_normal.png",material_texture="material_test_metal.png"},14)
core.register_node("material_shading_test:cutout", {
 drawtype="allfaces",paramtype="light",use_texture_alpha="clip",groups={cracky=1},
 tiles={{name="material_test_cutout.png",normal_texture="material_test_normal.png",material_texture="material_test_metal.png"}},
})
-- No explicit fields: a texture pack may add companions with these names.
register("auto","material_test_auto.png")
register("animated",{name="material_test_animated.png",normal_texture="material_test_animated_normal.png",
 material_texture="material_test_animated_orm.png",animation={type="vertical_frames",aspect_w=16,aspect_h=16,length=1}})
core.register_on_joinplayer(function(player)
 core.emerge_area({x=-16,y=-8,z=-16},{x=16,y=16,z=16},function(_,_,remaining)
  if remaining~=0 then return end
  core.after(0,function()
   local vm=VoxelManip()
   local minp,maxp=vm:read_from_map({x=-16,y=-8,z=-16},{x=16,y=16,z=16})
   local area=VoxelArea:new({MinEdge=minp,MaxEdge=maxp})
   local data=vm:get_data()
   local air,stone=core.get_content_id("air"),core.get_content_id("basenodes:stone")
   for z=-16,16 do for y=-8,16 do for x=-16,16 do data[area:index(x,y,z)]=y<=0 and stone or air end end end
   vm:set_data(data);vm:write_to_map()
   for i,name in ipairs({"rough","metal","auto","animated"}) do
    for y=1,3 do core.set_node({x=(i-1)*3-4,y=y,z=4},{name="material_shading_test:"..name}) end
   end
   core.set_node({x=0,y=1,z=1},{name="material_shading_test:emissive"})
   core.set_node({x=2,y=2,z=1},{name="material_shading_test:cutout"})
   core.log("action","Material integration: cutout normal/ORM node placed")
   player:set_pos({x=0,y=2,z=-5});player:set_look_horizontal(0);player:set_look_vertical(0.1)
   player:set_physics_override({gravity=0,speed=0});core.set_timeofday(0.32)
   player:set_lighting({shadows={intensity=0.65,direction={x=0.4,y=1,z=-0.5}},volumetric_light={strength=0.15}})
   core.log("action","Material integration: authored, companion and animated nodes placed")
   local stages = {{name="baseline", run=function() end}}
   local function add(name, run) stages[#stages+1]={name=name,run=run} end
   if core.settings:get_bool("material_test_directional",false) then
    add("zero shadow strength",function()
     player:set_lighting({shadows={intensity=0,direction={x=0.4,y=1,z=-0.5}}})
    end)
    add("hidden sky lights",function()
     player:set_lighting({shadows={intensity=0,direction={x=0,y=0,z=0}}})
     player:set_sun({visible=false});player:set_moon({visible=false})
    end)
    add("visible sun",function()
     core.set_timeofday(0.5);player:set_sun({visible=true})
    end)
    add("visible moon",function()
     core.set_timeofday(0);player:set_moon({visible=true})
    end)
    add("custom light restored",function()
     player:set_lighting({shadows={intensity=0.65,direction={x=0.4,y=1,z=-0.5}}})
    end)
   end
   if core.settings:get_bool("material_test_dynamic_light",false) then
    add("held light",function()
     assert(player:set_wielded_item("material_shading_test:emissive"))
     core.log("action","Material integration: held light")
    end)
    add("removed held light",function()
     assert(player:set_wielded_item(""))
     core.log("action","Material integration: removed held light")
    end)
   end
   add("unmapped replacement",function()
    -- Swapping in the same mesh must clear stale material-map bindings.
    for y=1,3 do core.set_node({x=-1,y=y,z=4},{name="basenodes:stone"}) end
    player:set_fov(70,false,0.2)
   end)
   local index=0
   local function advance()
    index=index+1
    local stage=stages[index]
    if not stage then core.request_shutdown("Material integration done",false,0);return end
    stage.run()
    core.log("action","Material directional integration: "..stage.name)
    core.log("action","Material stage: "..core.write_json({index=index,name=stage.name,time_us=core.get_us_time()},false))
    local function wait_frames()
     if core.settings:get_bool("material_test_wait_client",false) then
      local file=io.open(core.get_worldpath().."/material-stage-"..index.."-ready","r")
      if not file then core.after(0.1,wait_frames);return end
      file:close()
     end
     advance()
    end
    core.after(2,wait_frames)
   end
   advance()
  end)
 end)
end)
