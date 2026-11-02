-- Luanti
-- SPDX-License-Identifier: LGPL-2.1-or-later
-- Keep old native baselines reproducible while Minetest Game is the main target.
if core.get_modpath("mcl_core") then
 graphics_test_game = {
  id="voxelibre",grass="mcl_core:dirt_with_grass",lamp="mcl_nether:glowstone",torch="mcl_torches:torch",
  forests={Forest=true,BirchForest=true,FlowerForest=true},
  forest_floors={"mcl_core:dirt_with_grass"},
  waters={"mclx_core:river_water_source","mcl_core:water_source"},river="mclx_core:river_water_source",
 }
else
 assert(core.get_modpath("default"),"Native renderer fixtures require Minetest Game or VoxeLibre")
 graphics_test_game = {
  id="minetest",grass="default:dirt_with_grass",lamp="default:meselamp",torch="default:torch",
  forests={deciduous_forest=true,coniferous_forest=true,rainforest=true},
  forest_floors={"default:dirt_with_grass","default:dirt_with_snow",
   "default:dirt_with_rainforest_litter","default:dirt_with_coniferous_litter"},
  waters={"default:river_water_source","default:water_source"},river="default:river_water_source",
 }
end
function graphics_test_game.freeze_environment()
 if core.get_modpath("vl_tuning") then
  for _,name in ipairs({"gamerule:doMobSpawning","gamerule:doWeatherCycle"}) do
   assert(vl_tuning.registered_settings[name]):set(false)
  end
 end
 if core.get_modpath("mcl_weather") then mcl_weather.change_weather("none") end
 core.clear_objects({mode="full"})
end
