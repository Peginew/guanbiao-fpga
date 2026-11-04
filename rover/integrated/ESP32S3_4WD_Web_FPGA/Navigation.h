#pragma once
#include <stdint.h>
#include "PathPlan.h"
enum class NavStage : uint8_t { Idle, Turning, Settling, Driving, Arrived, Cancelled, Failed, DistanceCompleted };
struct NavigationState {
  NavStage stage=NavStage::Idle;
  float goalX=0,goalY=0,speed=80,errorMm=0;
  float startX=0,startY=0;
  uint32_t startedMs=0,settleSinceMs=0;
  const char *reason="none";
  PathPlan plan;
  uint8_t index=0;
  // Capture the failed wheel before stopVehicle zeros all live outputs.
  uint8_t feedbackMotor=0;
  float feedbackTarget=0,feedbackDuty=0;
  uint32_t feedbackSilenceMs=0,feedbackCount=0;
  bool nextLegPending=false,distanceOnlyUsed=false,previousDistanceOnly=false;
  uint32_t deadlineMs=90000;
};
constexpr float NAV_COORD_LIMIT_MM=PathLimits::COORD_MM;
constexpr float NAV_MAX_LEG_MM=PathLimits::LEG_MM;
constexpr float NAV_MIN_SPEED=PathLimits::MIN_SPEED,NAV_MAX_SPEED=PathLimits::MAX_SPEED;
constexpr float NAV_POSITION_TOL_MM=20;
constexpr uint32_t NAV_MAX_TASK_MS=90000,NAV_SETTLE_TIMEOUT_MS=2500;
constexpr uint32_t NAV_FG_TIMEOUT_MS=1500;
