/*
  ESP32-S3 three-wheel chassis: M1/M2 drive, passive front caster, Arduino-ESP32 3.x
  2 x 6-wire BLDC geared motors with built-in controllers. M3/M4 inactive.
  BLUE  = active LOW PWM, recommended 20..30kHz. HIGH = stopped.
  WHITE = HIGH or floating CCW / LOW CW. Do not switch while running.
  GREEN = HIGH or floating run / LOW brake.
  YELLOW = FG NPN open collector: external 10k pullup to 3.3V.
  RED/BLACK = external 8..24V motor supply; never connect to ESP32 supply.

  Install via Arduino IDE: select ESP32S3 Dev Module, Arduino-ESP32 3.x.
  Enable "USB CDC On Boot" if using ESP32-S3 native USB Serial.
  Uses only built-in libraries: WiFi.h and ESP-IDF esp_http_server.
*/

#include <Arduino.h>
#include <WiFi.h>
#ifdef ARDUINO
#include "NativeHttpServer.h"
#include <esp_system.h>
#else
#include <WebServer.h>
#endif
#include "BufferedConsole.h"
#include <math.h>
#include <ctype.h>
#include <driver/gpio.h>
#include <driver/uart.h>
#include <esp_random.h>
#include "CarConfig.h"
#include "Calibration.h"
#include "Stage1Control.h"
#include "LineBuffer.h"
#include "RxProbe.h"
#include "WebBridge.h"
#include "ImuHeading.h"
#include "ImuMotion.h"
#include "RouteSpeed.h"
#include "GoalDrive.h"
#include "WheelPid.h"
#include "MotorStartAssist.h"
// R24 outputs require explicit local arm, an exclusive owner and fresh V4/sensors.
constexpr bool LINK_DIAGNOSTIC_ONLY = false;
InspectionExecutor inspection;
ScanPlan scanPlan;
bool scanLaunchPending=false,scanAlignStarted=false,scanDwellStarted=false;
uint32_t scanDwellAt=0,scanPointAt=0;float inspectionArrivalHeading=0;
bool inspectionOutputPermit();
void serviceInspectionOutputs();
void confirmInspectionDriveStarted();
WheelPiProfile wheelPi;
using CarConfig::FPGA_RX; using CarConfig::RESERVED_TX; using CarConfig::FORWARD_HIGH; using CarConfig::TEST_DUTY_PERCENT;

// ============================================================================
// 1) CONFIGURATION: ONLY EDIT THIS SECTION FOR HARDWARE / CHASSIS CALIBRATION
// ============================================================================

enum Wheel : uint8_t { FL = 0, FR = 1, RL = 2, RR = 3, MOTOR_COUNT = 4 };
const char *const WHEEL_NAME[MOTOR_COUNT] = {"M1", "M2", "M3", "M4"};
// FL/FR/RL/RR enum names retain historical raw channel indices only.
// Use these logical-side indices for BOTH commands and odometry.
constexpr uint8_t LEFT_A=CarConfig::LEFT_MOTOR, LEFT_B=CarConfig::LEFT_MOTOR;
constexpr uint8_t RIGHT_A=CarConfig::RIGHT_MOTOR, RIGHT_B=CarConfig::RIGHT_MOTOR;
constexpr float MAX_TURN_WHEEL_MM_S=60.0f;
// ESP32-S3 raw channel pin assignments: M1..M4. Physical front/rear not remapped.
// Avoid GPIO0/3/19/20/35..37/43..46 for this S3 reference design.
constexpr auto &PIN_PWM = CarConfig::PWM;
constexpr auto &PIN_DIR = CarConfig::DIR;
constexpr auto &PIN_BRK = CarConfig::BRK;
constexpr auto &PIN_FG  = CarConfig::FG;

// Change these after a wheels-off-the-ground direction test.
// TRUE: a HIGH white direction input makes this wheel drive forward.
// Starting assumption: left and right gearboxes are mirror-mounted.
constexpr auto &FORWARD_IS_CCW = CarConfig::FORWARD_HIGH;

// Sheet says 6 FG pulses/round. ASSUMPTION: 6 per MOTOR (pre-reducer)
// shaft revolution, so 6 * 30 = 180 falling edges/output revolution.
// If the 6 pulses refer to the output shaft, set FG_ON_MOTOR_SHAFT=false.
constexpr float FG_PULSES_PER_REV = 6.0f;
constexpr float GEAR_RATIO = 30.0f;
constexpr bool FG_ON_MOTOR_SHAFT = true;
constexpr float WHEEL_DIAMETER_MM = 68.0f;
constexpr float WHEELBASE_MM = 130.0f;       // front-to-rear: recorded geometry
constexpr float TRACK_PHYSICAL_MM = 180.0f;  // left-to-right wheel center distance
constexpr float TRACK_EFFECTIVE_MM = FieldCalibration::EFFECTIVE_TRACK_MM; // R1 coarse field fit, not physical width

// Motor electrical behavior from supplied controller specification.
constexpr uint32_t PWM_FREQ_HZ = CarConfig::PWM_HZ;
constexpr uint8_t PWM_BITS = CarConfig::PWM_BITS;
constexpr uint16_t PWM_MAX = CarConfig::PWM_MAX;
constexpr bool PWM_ACTIVE_LOW = true;       // crucial! 
constexpr bool BRAKE_ACTIVE_LOW = true;
constexpr bool CCW_INPUT_HIGH = true;

// Motion limits and tuning: adjust after measuring actual vehicle speed.
constexpr float MAX_WHEEL_MM_S = 350.0f;    // initial conservative estimate
constexpr float DEFAULT_MOVE_MM_S = 40.0f;
constexpr float DEFAULT_TURN_MM_S = 40.0f; // outer wheel speed for turns
constexpr float WEB_MAX_LINEAR_MM_S = 220.0f;
constexpr float WEB_MAX_ANGULAR_DEG_S = 160.0f;
constexpr float ACCEL_MM_S2 = 450.0f;
constexpr float PROFILE_BRAKE_MM_S2 = 300.0f;
constexpr float POSITION_TOL_MM = 2.5f;
constexpr float PROFILE_MIN_CREEP_MM_S = 35.0f;

// Encoder velocity PI control; PID_KP in % duty / (mm/s),
// PID_KI in % duty / (mm/s * s). Calibrate feedforward first.
constexpr bool ENABLE_SPEED_PI = true;
constexpr float MOTOR_SPEED_AT_FULL_DUTY_MM_S = 350.0f;
constexpr float MOTOR_MIN_DUTY_PCT = 12.0f;
constexpr float MOTOR_MAX_DUTY_PCT = 100.0f;
constexpr float PID_KP = 0.12f;
constexpr float PID_KI = 0.25f;

constexpr uint32_t CONTROL_PERIOD_MS = 50;
constexpr uint32_t DIRECTION_BRAKE_MS = 180;
constexpr uint32_t DIRECTION_QUIET_MS = 150;
constexpr uint32_t MANUAL_WATCHDOG_MS = 650;
constexpr uint32_t STALL_TIMEOUT_MS = 1800;
constexpr float STALL_SPEED_THRESHOLD_MM_S = 65.0f;
constexpr bool ENABLE_STALL_GUARD = true;

// Phone R2: password-protected AP, no separate HTTP login.
const char *const FIRMWARE_VERSION = "S3-THREE-WHEEL-SCAN-LITE-R24-20261103";
const char *const AP_SSID = "S3-4WD-Car";
const char *const AP_PASSWORD = "ChangeCar123"; // >= 8 chars; change!

// ============================================================================
// 2) MOTOR DRIVER / ENCODER / ODOMETRY
// ============================================================================

constexpr float PI_F = 3.14159265358979323846f;
constexpr float DEG2RAD = PI_F / 180.0f;
constexpr float RAD2DEG = 180.0f / PI_F;
constexpr float OUTPUT_PULSES_PER_REV = FG_PULSES_PER_REV *
                                       (FG_ON_MOTOR_SHAFT ? GEAR_RATIO : 1.0f);
constexpr float MM_PER_PULSE = PI_F * WHEEL_DIAMETER_MM / OUTPUT_PULSES_PER_REV * FieldCalibration::DISTANCE_SCALE;

volatile uint32_t fgCount[MOTOR_COUNT] = {0, 0, 0, 0};
#include "FgInterrupts.inc"
void IRAM_ATTR fgFL() { ++fgCount[FL]; }
void IRAM_ATTR fgFR() { ++fgCount[FR]; }
void IRAM_ATTR fgRL() { ++fgCount[RL]; }
void IRAM_ATTR fgRR() { ++fgCount[RR]; }

struct MotorState {
  uint32_t lastCount = 0;
  uint32_t lastPulseMs = 0;
  uint32_t switchStartMs = 0;
  uint32_t driveStartMs = 0;
  uint32_t startCount=0,startDelayMs=0xffffffffu;
  bool startAssistActive=false;
  int8_t directionSign = +1;
  bool switching = false;
  bool driven = false;
  float targetMmS = 0;
  float rampMmS = 0;
  float measuredMmS = 0;
  float distanceMm = 0;
  float integral = 0;
  float previousSpeedAbs=0,filteredAcceleration=0;
  bool derivativeReady=false;
  float dutyPercent = 0;
};
MotorState motor[MOTOR_COUNT];

float xMm = 0, yMm = 0, thetaRad = 0;
float avgLeftMm = 0, avgRightMm = 0;
float actualLeftMmS = 0, actualRightMmS = 0;
uint32_t lastControlMs = 0,poseFrame=1;

#ifdef ARDUINO
NativeHttpServer server(80);
#else
WebServer server(80);
#endif
BufferedConsole console;
uint32_t loopLastMs=0,loopMaxGapMs=0,bootResetReason=0;
bool apStarted=false,httpStarted=false;
#include "AppState.inc"

enum class Mode : uint8_t { Idle, Manual, Segment, Pulse };
enum class Fault : uint8_t { None, EStop, Stall, SegmentTimeout, Hardware, Navigation, Route, Imu, MotionResponse };
// Declare explicitly so Arduino does not generate a prototype before Fault exists.
void setFault(Fault f);

Mode mode = Mode::Idle;
Fault fault = Fault::None;
uint32_t manualLastMs = 0;
float manualLinearMmS = 0, manualTurnMmS = 0;
bool pairReversePending=false;uint32_t pairReverseSinceMs=0;

struct Segment {
  float startL = 0, startR = 0;
  float goalL = 0, goalR = 0;    // signed expected wheel travel
  float maxSpeedMmS = 0;        // max speed of the longer-path side
  uint32_t startedMs = 0;
  uint32_t deadlineMs = 0;
  const char *label = "none";
} segment;
ImuHeading imu;
struct ImuLinkState {uint32_t portMs=0,lastRestartMs=0,restarts=0;uint8_t autoRestarts=0;} imuLink;
ImuMotionState imuMotion;
GoalDriveState goalDrive;
HeadingFeedback headingFeedback;
struct ImuFaultEvidence {bool valid=false;uint32_t age=0,bad=0,timeouts=0;float roll=0,pitch=0,travelL=0,travelR=0,command=0,duty=0;} imuFault;
float manualHeadingDeg=0;
StraightStability::Steering manualSteering;
bool poseZeroed=false;
void initImuSegment(float left,float right);
void serviceImu();

static inline float clampf(float v, float lo, float hi) {
  if (v < lo) return lo;
  if (v > hi) return hi;
  return v;
}
static inline int8_t signf(float v) { return v > 0.001f ? +1 : (v < -0.001f ? -1 : 0); }
static inline bool isFiniteNumber(float v) { return isfinite(v); }

const char *modeName() {
  if(routeActive()&&mode==Mode::Idle)return routeStageName();
  if(navigation.stage==NavStage::Settling)return "goto-settle";
  switch (mode) {
    case Mode::Idle: return "idle";
    case Mode::Manual: return "manual";
    case Mode::Pulse: return "fpga-test";
    default: return segment.label;
  }
}
const char *faultName() {
  switch (fault) {
    case Fault::None: return "none";
    case Fault::EStop: return "e-stop";
    case Fault::Stall: return "encoder-stall";
    case Fault::Hardware: return "io-fault";
    case Fault::Navigation: return "navigation-failed";
    case Fault::Route: return "route-failed";
    case Fault::Imu: return "imu-failed";
    case Fault::MotionResponse: return "motion-response";
    default: return "motion-timeout";
  }
}

void writeBrake(uint8_t i, bool engage) {
  if(!CarConfig::motorEnabled(i))return;
  if(!engage&&!inspectionOutputPermit())engage=true;
  if (!engage && (!hardwareReady || ioFault || fault != Fault::None || control.estop)) engage=true;
  digitalWrite(PIN_BRK[i], (engage == BRAKE_ACTIVE_LOW) ? LOW : HIGH);
}
void writeDirection(uint8_t i, int8_t forwardSign) {
  if(!CarConfig::motorEnabled(i))return;
  const bool ccw = (forwardSign > 0) ? FORWARD_IS_CCW[i] : !FORWARD_IS_CCW[i];
  const bool highLevel = (ccw == CCW_INPUT_HIGH);
  digitalWrite(PIN_DIR[i], highLevel ? HIGH : LOW);
  motor[i].directionSign = forwardSign;
}
void writeDuty(uint8_t i, float drivePercent) {
  if(!CarConfig::motorEnabled(i)){motor[i].dutyPercent=0;return;}
  if(!inspectionOutputPermit())drivePercent=0;
  const float normalized = clampf(drivePercent, 0, 100) / 100.0f;
  const uint16_t onDuty = uint16_t(lroundf(normalized * PWM_MAX));
  // LEDC duty is time HIGH. Our motor accelerates during time LOW.
  if (attached[i]) {
    if (!ledcWrite(PIN_PWM[i], PWM_ACTIVE_LOW ? (PWM_MAX - onDuty) : onDuty)) {
      if(!ioFault){faultSource="pwm-write";stopSource="pwm-write";}
      ioFault=true;hardwareReady=false;fault=Fault::Hardware;
      control.emergencyStop();mode=Mode::Idle;owner=Source::None;
      for (uint8_t j=0;j<MOTOR_COUNT;j++)if(CarConfig::motorEnabled(j))digitalWrite(PIN_BRK[j],LOW);
      // Assert brakes first; stop every healthy PWM without recursively calling
      // writeDuty when one LEDC write has failed.
      for (uint8_t j=0;j<MOTOR_COUNT;j++) {
        if(!CarConfig::motorEnabled(j))continue;
        if(attached[j])ledcWrite(PIN_PWM[j],PWM_MAX);
        else digitalWrite(PIN_PWM[j],HIGH);
        motor[j].targetMmS=motor[j].rampMmS=motor[j].integral=motor[j].dutyPercent=0;
        motor[j].driven=motor[j].switching=false;
      }
      return;
    }
  } else digitalWrite(PIN_PWM[i],HIGH);
  motor[i].dutyPercent = drivePercent;
}

void brakeAllImmediately() {
  for (uint8_t i=0;i<MOTOR_COUNT;i++) writeBrake(i,true);
  for (uint8_t i = 0; i < MOTOR_COUNT; i++) {
    writeBrake(i, true);
    writeDuty(i, 0);
    motor[i].targetMmS = 0;
    motor[i].rampMmS = 0;
    motor[i].integral = 0;
    motor[i].switching = false;
    motor[i].driven = false;
    motor[i].startAssistActive=false;
  }
}
void invalidateFpgaObservationOnStop();
void stopVehicle(const char *source="control") {
  invalidateFpgaObservationOnStop();
  stopSource=source;
  portENTER_CRITICAL(&webMux);webLeaseToken[0]=0;portEXIT_CRITICAL(&webMux);
  cancelNavigation();
  cancelRoute(source);
  control.stop();
  ++webEpoch;
  stoppedSinceMs=millis();
  owner=Source::None;
  mode = Mode::Idle;
  manualLinearMmS = manualTurnMmS = 0;pairReversePending=false;
  manualSteering=StraightStability::Steering{};
  imuMotion=ImuMotionState{};
  brakeAllImmediately();
}
void setFault(Fault f) {
  if (fault == Fault::None) {fault = f;faultSource="control";}
  stopVehicle();
  if (f==Fault::EStop) control.emergencyStop();
  console.printf("FAULT %s\n", faultName());
}

void setWheelTargets(float left,float right) {
  if(!inspectionOutputPermit())left=right=0;
  const float peak=fmaxf(fabsf(left),fabsf(right));
  if(peak>WEB_MAX_LINEAR_MM_S){left*=WEB_MAX_LINEAR_MM_S/peak;right*=WEB_MAX_LINEAR_MM_S/peak;}
  for(auto &m:motor)m.targetMmS=0;
  motor[CarConfig::LEFT_MOTOR].targetMmS=clampf(left,-WEB_MAX_LINEAR_MM_S,WEB_MAX_LINEAR_MM_S);
  motor[CarConfig::RIGHT_MOTOR].targetMmS=clampf(right,-WEB_MAX_LINEAR_MM_S,WEB_MAX_LINEAR_MM_S);
}

void captureMissingWheelFeedback(uint8_t i,uint32_t now) {
  navigation.feedbackMotor=i+1;
  navigation.feedbackTarget=motor[i].targetMmS;
  navigation.feedbackDuty=motor[i].dutyPercent;
  navigation.feedbackSilenceMs=uint32_t(now-motor[i].lastPulseMs);
  navigation.feedbackCount=fgCount[i];
}

float currentSideTravel(uint8_t a, uint8_t b) {
  return 0.5f * (motor[a].distanceMm + motor[b].distanceMm);
}

void sampleEncodersAndOdometry(float dtSec, uint32_t now) {
  uint32_t count[MOTOR_COUNT];
  noInterrupts();
  for (uint8_t i = 0; i < MOTOR_COUNT; i++) count[i] = fgCount[i];
  interrupts();

  for (uint8_t i = 0; i < MOTOR_COUNT; i++) {
    if(!CarConfig::motorEnabled(i)){motor[i].lastCount=count[i];motor[i].measuredMmS=motor[i].distanceMm=0;continue;}
    const uint32_t pulses = count[i] - motor[i].lastCount; // handles wrap
    motor[i].lastCount = count[i];
    if (pulses) motor[i].lastPulseMs = now;
    const float deltaMm = pulses * MM_PER_PULSE;
    // Single FG channel has no direction: sign is inferred from the driver.
    motor[i].distanceMm += deltaMm * motor[i].directionSign;
    const float instantSpeed = deltaMm / dtSec * motor[i].directionSign;
    motor[i].measuredMmS = 0.65f * motor[i].measuredMmS + 0.35f * instantSpeed;
  }

  const float l = currentSideTravel(LEFT_A, LEFT_B);
  const float r = currentSideTravel(RIGHT_A, RIGHT_B);
  const float dL = l - avgLeftMm, dR = r - avgRightMm;
  avgLeftMm = l;
  avgRightMm = r;
  actualLeftMmS = 0.5f * (motor[LEFT_A].measuredMmS + motor[LEFT_B].measuredMmS);
  actualRightMmS = 0.5f * (motor[RIGHT_A].measuredMmS + motor[RIGHT_B].measuredMmS);
  const float ds = 0.5f * (dL + dR);
  // Heading comes from the real UART2 IMU. FG only measures wheel travel.
  const float nextHeading=ImuConfig::ENABLED && imu.usable(now)?imu.headingDeg()*DEG2RAD:thetaRad+(dR-dL)/TRACK_EFFECTIVE_MM;
  const float da=atan2f(sinf(nextHeading-thetaRad),cosf(nextHeading-thetaRad));
  xMm += ds * cosf(thetaRad + 0.5f * da);
  yMm += ds * sinf(thetaRad + 0.5f * da);
  thetaRad = atan2f(sinf(thetaRad + da), cosf(thetaRad + da));
}

void recordHeading(const char *phase,float target,uint8_t corrections=0) {
  headingFeedback.valid=true;headingFeedback.phase=phase;
  headingFeedback.target=target;headingFeedback.actual=imu.headingDeg();
  headingFeedback.error=target-headingFeedback.actual;headingFeedback.corrections=corrections;
}
void limitHeading(const char *note) {
  headingFeedback.limited=true;headingFeedback.note=note;
  headingFeedback.residual=headingFeedback.error;
}
// Precision limits cancel normally; invalid sensor/IO/FG still use real faults.
void stopForHeading(const char *reason,float target,uint8_t corrections=0) {
  recordHeading("stopped",target,corrections);limitHeading(reason);
  const bool hadRoute=routeActive(),hadNav=navigationActive();
  stopVehicle(reason);
  if(hadRoute)route.reason=reason;
  if(hadNav)navigation.reason=reason;
  statusPending=true;
}
bool startManual(float linearMmS,float yawDegS) {
  // R20 restores the R15 joystick API: v=mm/s, w=degrees/second.
  // Keep R19's bounded wheel differential, including mixed joystick commands.
  if(requestSource!=Source::Web||!isFiniteNumber(linearMmS)||!isFiniteNumber(yawDegS)||
     fabsf(linearMmS)>WEB_MAX_LINEAR_MM_S||fabsf(yawDegS)>WEB_MAX_ANGULAR_DEG_S)return false;
  const float turnWheelMmS=clampf(yawDegS*DEG2RAD*TRACK_EFFECTIVE_MM*.5f,-MAX_TURN_WHEEL_MM_S,MAX_TURN_WHEEL_MM_S);
  if(!canRequestMotion()||mode==Mode::Segment||fault!=Fault::None)return false;
  if(linearMmS==0&&turnWheelMmS==0){if(consoleMode){brakeAllImmediately();mode=Mode::Idle;owner=Source::Web;manualLinearMmS=manualTurnMmS=0;manualSteering=StraightStability::Steering{};imuMotion=ImuMotionState{};return !ioFault;}stopVehicle("manual-zero");return true;}
  const bool newStraight=turnWheelMmS==0 && linearMmS!=0 &&
    (mode!=Mode::Manual||manualTurnMmS!=0||signf(manualLinearMmS)!=signf(linearMmS));
  if(mode!=Mode::Manual||newStraight){headingFeedback=HeadingFeedback{};manualSteering=StraightStability::Steering{};}
  if(newStraight)manualHeadingDeg=imu.headingDeg();
  const float left=linearMmS-turnWheelMmS,right=linearMmS+turnWheelMmS;
  const bool reverse=(signf(left)&&signf(left)!=motor[LEFT_A].directionSign)||
    (signf(right)&&signf(right)!=motor[RIGHT_A].directionSign);
  if(reverse&&!pairReversePending){pairReversePending=true;pairReverseSinceMs=millis();}
  manualLinearMmS=linearMmS;manualTurnMmS=turnWheelMmS;
  manualLastMs=millis();owner=requestSource;mode=Mode::Manual;return true;
}
bool startSegment(float leftMm,float rightMm,float wheelSpeed,const char *label) {
  // Public finite commands and accepted route/path steps share one motor owner.
  if((requestSource!=Source::Web&&!(requestSource==Source::ScanApproach&&scanPlan.running()&&inspectionNavigation))||!poseZeroed||
     !canRequestMotion()||mode==Mode::Segment||fault!=Fault::None)return false;
  if(!navigationInternal&&!routeInternal&&(mode!=Mode::Idle||navigationActive()||routeActive()))return false;
  const float maxTravel=routeInternal?RouteLimits::MAX_MOVE_MM+NAV_POSITION_TOL_MM:
    navigationInternal?NAV_MAX_LEG_MM+NAV_POSITION_TOL_MM:NAV_MAX_LEG_MM;
  if(!isFiniteNumber(leftMm)||!isFiniteNumber(rightMm)||!isFiniteNumber(wheelSpeed)||
     wheelSpeed<20.0f||wheelSpeed>WEB_MAX_LINEAR_MM_S||
     fmaxf(fabsf(leftMm),fabsf(rightMm))>maxTravel)return false;
  const bool straight=fabsf(leftMm-rightMm)<.001f;
  const bool turn=fabsf(leftMm+rightMm)<.001f;
  (void)straight; // Unequal same-direction endpoints implement finite arcs.
  if(turn)wheelSpeed=fminf(wheelSpeed,MAX_TURN_WHEEL_MM_S);
  brakeAllImmediately();if(ioFault)return false;
  segment.startL=avgLeftMm;segment.startR=avgRightMm;
  segment.goalL=leftMm;segment.goalR=rightMm;segment.maxSpeedMmS=wheelSpeed;
  segment.startedMs=millis();segment.deadlineMs=uint32_t(64000.0f+
    4000.0f*fmaxf(fabsf(leftMm),fabsf(rightMm))/fmaxf(35.0f,wheelSpeed));
  segment.label=label;initImuSegment(leftMm,rightMm);
  owner=requestSource;mode=Mode::Segment;return true;
}

bool moveMm(float signedMm, float speed = DEFAULT_MOVE_MM_S) {
  return startSegment(signedMm, signedMm, speed, "move");
}
bool turnDeg(float signedDeg, float speed = DEFAULT_TURN_MM_S) {
  if(!isFiniteNumber(signedDeg)||fabsf(signedDeg)>360.0f)return false;
  // Positive deg = CCW / left: left wheels reverse, right wheels forward.
  const float sideTravel = TRACK_EFFECTIVE_MM * 0.5f * signedDeg * DEG2RAD;
  return startSegment(-sideTravel, sideTravel, speed, "turn");
}
bool arcMmDeg(float radiusMm, float signedDeg, float speed = DEFAULT_MOVE_MM_S) {
  if (!isFiniteNumber(radiusMm) || !isFiniteNumber(signedDeg) ||
      radiusMm < TRACK_EFFECTIVE_MM * 0.5f || radiusMm > 10000 || fabsf(signedDeg)>360.0f) return false;
  const float angle = signedDeg * DEG2RAD;
  const float l = (radiusMm - TRACK_EFFECTIVE_MM / 2.0f) * angle;
  const float r = (radiusMm + TRACK_EFFECTIVE_MM / 2.0f) * angle;
  return startSegment(l, r, speed, "arc");
}

float profiledSideSpeed(float goal, float traveled, float ratio, float mainSpeed,
                        float tolerance=POSITION_TOL_MM) {
  if (fabsf(goal) < 0.001f) return 0;
  const float forwardProgress = traveled * signf(goal);
  const float left = fabsf(goal) - forwardProgress;
  if (left <= tolerance) return 0;
  const bool fastRoute=routeActive()&&route.plan.speed>120;
  const float speedForBraking = fastRoute?RouteSpeed::brakingSpeed(left):sqrtf(2.0f * PROFILE_BRAKE_MM_S2 * left);
  const float maxSide = fmaxf(PROFILE_MIN_CREEP_MM_S, mainSpeed * ratio);
  const float speed = clampf(speedForBraking, PROFILE_MIN_CREEP_MM_S, maxSide);
  return signf(goal) * speed;
}

void completeImuSegment(uint32_t now);
void turnResponseFault(uint32_t now);
#include "GoalDriveRuntime.inc"
#include "ImuRuntime.inc"

void calculateTargets(uint32_t now) {
  if (fault != Fault::None) { setWheelTargets(0, 0); return; }
  if(owner==Source::Inspection){serviceInspectionOutputs();return;}
  if(mode==Mode::Manual&&uint32_t(now-manualLastMs)>MANUAL_WATCHDOG_MS){stopVehicle("manual-timeout");return;}
  if(ImuConfig::ENABLED&&(mode==Mode::Manual||mode==Mode::Segment)) {
    if(!imu.usable(now)){imuMotionFault(imu.reason(now));return;}
    if(!imu.ready(now)){setWheelTargets(0,0);return;}
  }
  // FG protection is independent of heading/IMU control, including low speeds.
  if(mode==Mode::Manual||mode==Mode::Segment) {
    for(uint8_t i=0;i<4;i++)if(CarConfig::motorEnabled(i)&&motor[i].driven&&motor[i].dutyPercent>0&&
      uint32_t(now-motor[i].driveStartMs)>1500&&uint32_t(now-motor[i].lastPulseMs)>1500) {
      captureMissingWheelFeedback(i,now);
      if(navigationActive()) {
        navigation.reason="FG_MISSING";navigation.stage=NavStage::Failed;fault=Fault::Navigation;
      } else fault=Fault::Stall;
      faultSource="fg-missing";stopVehicle("fg-missing");statusPending=true;return;
    }
  }
  if(mode==Mode::Manual) {
    float left=manualLinearMmS-manualTurnMmS,right=manualLinearMmS+manualTurnMmS;
    if(manualTurnMmS==0&&manualLinearMmS!=0) {
      const float error=manualHeadingDeg-imu.headingDeg();recordHeading("straight",manualHeadingDeg);
      if(fabsf(error)>ImuMotion::HEADING_STOP_DEG){stopForHeading("heading-limit",manualHeadingDeg);return;}
      ImuMotion::straight(manualLinearMmS,error,left,right);
      const float delta=StraightStability::smooth(manualSteering,.5f*(right-left),imu.rateDegS,now,fabsf(manualLinearMmS)*.30f);
      left=manualLinearMmS-delta;right=manualLinearMmS+delta;
    } else manualSteering=StraightStability::Steering{};
    const float peak=fmaxf(fabsf(left),fabsf(right));
    if(peak>WEB_MAX_LINEAR_MM_S){left*=WEB_MAX_LINEAR_MM_S/peak;right*=WEB_MAX_LINEAR_MM_S/peak;}
    setWheelTargets(left,right);
    return;
  }
  if (mode == Mode::Segment) {
    if(!navigationObstacleSafe(now))return;
    if ((uint32_t)(now - segment.startedMs) > segment.deadlineMs) {
      setFault(Fault::SegmentTimeout);
      return;
    }
    if(calculateImuSegment(now))return;
    const float travelL = avgLeftMm - segment.startL;
    const float travelR = avgRightMm - segment.startR;
    const float maxGoal = fmaxf(fabsf(segment.goalL), fabsf(segment.goalR));
    if (maxGoal < 0.0001f) { stopVehicle("completed"); return; }
    const float ratioL = fabsf(segment.goalL) / maxGoal;
    const float ratioR = fabsf(segment.goalR) / maxGoal;
    const float tolerance=routeActive()?((route.aligning||route.plan.steps[route.index].kind=='T')?
      RouteLimits::TURN_TOL_MM:RouteLimits::MOVE_TOL_MM):POSITION_TOL_MM;
    float vL = profiledSideSpeed(segment.goalL, travelL, ratioL, segment.maxSpeedMmS,tolerance);
    float vR = profiledSideSpeed(segment.goalR, travelR, ratioR, segment.maxSpeedMmS,tolerance);
    if (vL == 0 && vR == 0) {
      if(routeActive())finishRouteSegment(now);
      else if(navigationActive())finishNavigationSegment(now);
      else {stopVehicle("completed");console.println("DONE");}
    } else {
      correctRouteStraight(vL,vR,travelL,travelR);
      setWheelTargets(vL, vR);
    }
    return;
  }
  setWheelTargets(0, 0);
}

void controlOneMotor(uint8_t i, float dt, uint32_t now) {
  MotorState &m = motor[i];
  if(!CarConfig::motorEnabled(i)){m=MotorState{};return;}
  const int8_t desiredSign = signf(m.targetMmS);
  if (desiredSign == 0) {
    writeBrake(i, true);
    writeDuty(i, 0);
    m.rampMmS = 0;
    m.integral = 0;
    m.derivativeReady=false;m.filteredAcceleration=0;
    m.driven = false;
    m.startAssistActive=false;
    m.switching = false;
    return;
  }

  // ALWAYS brake and wait for FG pulses to cease before reversing.
  if (desiredSign != m.directionSign || m.switching) {
    if (!m.switching) {
      m.switching = true;
      m.switchStartMs = now;
    }
    writeBrake(i, true);
    writeDuty(i, 0);
    m.rampMmS = 0;
    m.integral = 0;
    m.derivativeReady=false;m.filteredAcceleration=0;
    m.driven = false;
    m.startAssistActive=false;
    if ((uint32_t)(now - m.switchStartMs) >= DIRECTION_BRAKE_MS &&
        (uint32_t)(now - m.lastPulseMs) >= DIRECTION_QUIET_MS) {
      writeDirection(i, desiredSign);
      m.switching = false;
    } else {
      return;
    }
  }

  const float targetAbs = fabsf(m.targetMmS);
  const bool straightDrive=mode==Mode::Manual; // smooth both translation and turns
  const float delta = (straightDrive?StraightStability::ACCEL_MM_S2:ACCEL_MM_S2) * dt;
  const float rampAbs = clampf(targetAbs, fmaxf(0, fabsf(m.rampMmS) - delta),
                              fabsf(m.rampMmS) + delta);
  m.rampMmS = rampAbs * m.directionSign;
  if (!m.driven) {
    m.driveStartMs = now;
    m.startCount=fgCount[i];m.startDelayMs=0xffffffffu;
    m.driven = true;
    m.integral = 0;
  }
  const float error = rampAbs - fabsf(m.measuredMmS);
  if(m.startDelayMs==0xffffffffu&&uint32_t(fgCount[i]-m.startCount)>0)m.startDelayMs=uint32_t(now-m.driveStartMs);
  float baseDuty = MOTOR_MIN_DUTY_PCT +
                   (100.0f - MOTOR_MIN_DUTY_PCT) * rampAbs /
                   MOTOR_SPEED_AT_FULL_DUTY_MM_S;
  baseDuty = clampf(baseDuty, 0, MOTOR_MAX_DUTY_PCT);
  const float nextIntegral=ENABLE_SPEED_PI?clampf(m.integral+error*dt,-160,160):m.integral;
  const auto &gain=wheelPi.gains[i];
  const float measured=fabsf(m.measuredMmS);
  const float acceleration=m.derivativeReady?(measured-m.previousSpeedAbs)/dt:0;
  m.previousSpeedAbs=measured;m.derivativeReady=true;
  m.filteredAcceleration+=dt/(WHEEL_PID_D_TAU_S+dt)*(acceleration-m.filteredAcceleration);
  const float derivative=clampf(-gain.kd*m.filteredAcceleration,-WHEEL_PID_D_LIMIT_PCT,WHEEL_PID_D_LIMIT_PCT);
  const float correction = ENABLE_SPEED_PI ? (gain.kp * error + gain.ki * nextIntegral+derivative) : 0;
  const float demanded=baseDuty+correction;
  float duty = clampf(baseDuty + correction, 0, MOTOR_MAX_DUTY_PCT);
  // Limited, nonblocking breakaway assistance only when commanded motion
  // has produced no recent pulses. Never retries a failed task or bypasses
  // the 1500ms navigation feedback guard. Brake/STOP paths return above.
  const uint32_t quietMs=uint32_t(now-m.lastPulseMs);
  const uint32_t drivenMs=uint32_t(now-m.driveStartMs);
  if(mode==Mode::Segment && rampAbs>0 && quietMs>=200 && drivenMs>=200) {
    const uint32_t waiting=quietMs<drivenMs?quietMs:drivenMs;
    const float support=clampf(28.0f+float(waiting-200)*.012f,28.0f,38.0f);
    duty=fmaxf(duty,support);
  }
  m.startAssistActive=MotorStartAssist::eligible(i,m.startDelayMs!=0xffffffffu,drivenMs);
  float assistFloor=0;
  if(m.startAssistActive){
    assistFloor=fminf(MotorStartAssist::floor(drivenMs),m.dutyPercent+MotorStartAssist::DUTY_RISE_PER_SECOND*dt);
    duty=fmaxf(duty,assistFloor);
  }
  if(straightDrive){
    const float rise=m.startAssistActive?MotorStartAssist::DUTY_RISE_PER_SECOND:StraightStability::DUTY_RISE_PER_SECOND;
    duty=clampf(duty,fmaxf(0,m.dutyPercent-StraightStability::DUTY_FALL_PER_SECOND*dt),fminf(100,m.dutyPercent+rise*dt));
  }
  const bool assistPushing=m.startAssistActive&&duty>demanded+.01f;
  if(ENABLE_SPEED_PI&&!assistPushing&&(!straightDrive||StraightStability::acceptIntegral(error,demanded,duty)))m.integral=nextIntegral;
  writeDuty(i, duty);
  writeBrake(i, false);

  if (ENABLE_STALL_GUARD && rampAbs >= STALL_SPEED_THRESHOLD_MM_S &&
      duty >= 25.0f && uint32_t(now-m.driveStartMs)>STALL_TIMEOUT_MS &&
      uint32_t(now-m.lastPulseMs)>STALL_TIMEOUT_MS) {
    setFault(Fault::Stall); // brake all wheels before potentially blocking prints
  }
}

void controlStep() {
  const uint32_t now = millis();
  if ((uint32_t)(now - lastControlMs) < CONTROL_PERIOD_MS) return;
  const float dt = clampf((now - lastControlMs) * 0.001f, 0.001f, 0.25f);
  lastControlMs = now;
  sampleEncodersAndOdometry(dt, now);
  if (mode==Mode::Pulse) return; // Stage1 owns outputs until its 500ms deadline.
  calculateTargets(now);
  if(mode==Mode::Manual||mode==Mode::Segment) {
    bool reverse=false;
    for(uint8_t i=0;i<2;i++)if(signf(motor[i].targetMmS)!=0&&signf(motor[i].targetMmS)!=motor[i].directionSign)reverse=true;
    if(reverse&&!pairReversePending){pairReversePending=true;pairReverseSinceMs=now;}
  }
  if((mode==Mode::Manual||mode==Mode::Segment)&&pairReversePending){
    // Both wheels wait when either must reverse. Do not restart one wheel
    // while the other is still braking after a forward/turn transition.
    const int8_t leftSign=signf(motor[LEFT_A].targetMmS),rightSign=signf(motor[RIGHT_A].targetMmS);
    brakeAllImmediately();
    if(!leftSign&&!rightSign)return;
    if(uint32_t(now-pairReverseSinceMs)<DIRECTION_BRAKE_MS)return;
    for(uint8_t i=0;i<2;i++)if(uint32_t(now-motor[i].lastPulseMs)<DIRECTION_QUIET_MS)return;
    if(leftSign)writeDirection(LEFT_A,leftSign);
    if(rightSign)writeDirection(RIGHT_A,rightSign);
    pairReversePending=false;calculateTargets(now);
  }
  for (uint8_t i = 0; i < MOTOR_COUNT; i++) {
    if (fault != Fault::None) break;
    controlOneMotor(i, dt, now);
  }
  confirmInspectionDriveStarted();
}

void zeroPose() {
  if(++poseFrame==0)++poseFrame;
  ++webEpoch;
  xMm = yMm = thetaRad = 0;
  if(ImuConfig::ENABLED)imu.anchor(0);
  poseZeroed=true;headingFeedback=HeadingFeedback{};manualSteering=StraightStability::Steering{};
  // Do not reset pulse counters: only the pose coordinate system.
}


#include "RouteRuntime.inc"
#include "Navigation.inc"
bool anyMotion();
void snapshotFg(uint32_t counts[4]);
#include "FpgaRuntime.inc"
#include "Runtime.inc"
#include "WebUi.h"
#include "ConsoleUi.h"
#ifdef ARDUINO
#include "WebUiGzip.h"
#endif
#include "WebRuntime.inc"

