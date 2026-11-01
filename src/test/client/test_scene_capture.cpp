// Luanti
// SPDX-License-Identifier: LGPL-2.1-or-later
#include "catch.h"
#include "catch_amalgamated.hpp"
#include "irr_ptr.h"
#include <irrlicht.h>
#include <ISceneManager.h>
#include <ISceneNode.h>
#include <vector>
#include "client/render/pipeline.h"
#include "client/shadows/shadow_basis.h"
#include <cmath>

TEST_CASE("Shadow camera basis crosses noon without changing orientation abruptly", "[client][render][shadow]")
{
	v3f previous(0, 0, 1);
	for (int i = -1000; i <= 1000; ++i) {
		const float angle = i * 0.001f;
		const v3f direction(std::sin(angle), -std::cos(angle), 0);
		const auto up = stableShadowUp(direction, previous);
		CHECK(up.dotProduct(previous) > 0.999f);
		CHECK(std::abs(up.dotProduct(direction)) < 0.00001f);
		CHECK(up.getLength() == Catch::Approx(1.0f));
		previous = up;
	}
	// Gradual custom-source rotation also transports a valid perpendicular basis.
	for (int i = 0; i <= 1000; ++i) {
		const float angle = i * 0.003f;
		const v3f direction = v3f(std::sin(angle), -std::cos(angle), 0.7f).normalize();
		const auto up = stableShadowUp(direction, previous);
		if (i > 0)
			CHECK(up.dotProduct(previous) > 0.999f);
		CHECK(std::abs(up.dotProduct(direction)) < 0.00001f);
		previous = up;
	}
	for (const auto direction : {v3f(), v3f(0, 0, 1), v3f(0, 1, 0)}) {
		const auto up = stableShadowUp(direction, direction);
		CHECK(up.getLength() == Catch::Approx(1.0f));
		CHECK(std::abs(up.dotProduct(direction)) < 0.00001f);
	}
}

TEST_CASE("Screen output keeps the frame dimensions after a fixed-size prepass", "[client][render]")
{
	SIrrlichtCreationParameters params;
	params.DriverType = video::EDT_NULL;
	params.WindowSize = {800,600};
	irr_ptr<IrrlichtDevice> device(createDeviceEx(params));
	REQUIRE(device);
	auto *driver = device->getVideoDriver();
	PipelineContext context(device.get(),nullptr,nullptr,nullptr,video::SColor(0),{800,600});
	ScreenTarget output;
	// Cloud-shadow output updates the offscreen viewport before pipeline reset.
	driver->OnResize({256,256});
	output.reset(context);
	output.activate(context);
	CHECK(driver->getScreenSize() == core::dimension2du(800,600));
	// A later actual window resize is supplied by the next frame's context.
	context.target_size = v2u32(1280,720);
	driver->OnResize({128,128});
	output.reset(context);
	output.activate(context);
	CHECK(driver->getScreenSize() == core::dimension2du(1280,720));
}

namespace {
class OrderedNode : public scene::ISceneNode
{
	std::vector<int> &order;
	scene::E_SCENE_NODE_RENDER_PASS pass;
	core::aabbox3d<f32> box{-1, -1, -1, 1, 1, 1};
public:
	OrderedNode(scene::ISceneManager *manager, int id,
			scene::E_SCENE_NODE_RENDER_PASS pass, std::vector<int> &order) :
		ISceneNode(manager->getRootSceneNode(), manager, id), order(order), pass(pass)
	{
		setAutomaticCulling(scene::EAC_OFF);
	}
	void OnRegisterSceneNode() override
	{
		SceneManager->registerNodeForRendering(this, pass);
		ISceneNode::OnRegisterSceneNode();
	}
	void render() override { order.push_back(getID()); }
	const core::aabbox3d<f32> &getBoundingBox() const override { return box; }
};
}

TEST_CASE("Opaque scene capture precedes every transparent pass", "[client][render]")
{
	SIrrlichtCreationParameters params;
	params.DriverType = video::EDT_NULL;
	irr_ptr<IrrlichtDevice> device(createDeviceEx(params));
	REQUIRE(device);
	auto *scene = device->getSceneManager();
	std::vector<int> order;
	const scene::E_SCENE_NODE_RENDER_PASS passes[] = { scene::ESNRP_SKY_BOX,
		scene::ESNRP_SOLID, scene::ESNRP_TRANSPARENT,
		scene::ESNRP_TRANSPARENT_EFFECT, scene::ESNRP_GUI };
	int id = 0;
	for (const auto pass : passes)
		(new OrderedNode(scene, ++id, pass, order))->drop();
	scene->drawAll([&] { order.push_back(99); });
	CHECK(order == std::vector<int>{1, 2, 99, 3, 4, 5});
	order.clear();
	// A callback must not persist into another camera, menu, wield or next-frame draw.
	scene->drawAll();
	CHECK(order == std::vector<int>{1, 2, 3, 4, 5});
}
