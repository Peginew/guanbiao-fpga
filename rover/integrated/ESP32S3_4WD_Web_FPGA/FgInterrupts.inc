// Own the GPIO interrupt source for the four FG inputs. Arduino's per-pin
// service installs through an IPC callback on this SDK; the captured boot loop
// overflowed that 1024-byte IPC task during esp_intr_alloc(). Allocate directly
// on the calling robot-loop core instead. ISR and pulse counters stay on the
// same core, preserving the existing noInterrupts() snapshots.
#include <esp_intr_alloc.h>
#include <hal/gpio_ll.h>
#include <soc/gpio_struct.h>
#include <soc/interrupts.h>

static_assert(PIN_FG[0]<32&&PIN_FG[1]<32&&PIN_FG[2]<32&&PIN_FG[3]<32,
              "FG ISR supports GPIO bank 0; update it before moving FG pins");
constexpr uint32_t FG_INTERRUPT_MASK=(1u<<PIN_FG[0])|(1u<<PIN_FG[1]);
intr_handle_t fgInterruptHandle=nullptr;
uint32_t fgInterruptCore=0;
bool fgInterruptReady=false;

void IRAM_ATTR fgBankInterrupt(void *) {
  uint32_t pending=0;
  gpio_ll_get_intr_status(&GPIO,fgInterruptCore,&pending);
  pending&=FG_INTERRUPT_MASK;
  // Falling-edge status must be acknowledged BEFORE counting, so another
  // edge arriving during the handler remains pending for the next interrupt.
  gpio_ll_clear_intr_status(&GPIO,pending);
  if(pending&(1u<<PIN_FG[0]))++fgCount[0];
  if(pending&(1u<<PIN_FG[1]))++fgCount[1];
}
bool installFgInterrupts() {
  if(fgInterruptReady)return true;
  fgInterruptCore=xPortGetCoreID();
  for(unsigned i=0;i<2;i++) {
    gpio_ll_intr_disable(&GPIO,PIN_FG[i]);
    gpio_ll_set_intr_type(&GPIO,PIN_FG[i],GPIO_INTR_NEGEDGE);
  }
  gpio_ll_clear_intr_status(&GPIO,FG_INTERRUPT_MASK);
  // Exclusive GPIO source: do not add Arduino attachInterrupt() or install a
  // second GPIO ISR service elsewhere in this firmware. Check failures rather
  // than pretending that wheel feedback is available.
  const int flags=ESP_INTR_FLAG_IRAM|ESP_INTR_FLAG_LEVEL1|ESP_INTR_FLAG_INTRDISABLED;
  if(esp_intr_alloc(ETS_GPIO_INTR_SOURCE,flags,fgBankInterrupt,nullptr,&fgInterruptHandle)!=ESP_OK) {
    fgInterruptHandle=nullptr;return false;
  }
  for(unsigned i=0;i<2;i++)gpio_ll_intr_enable_on_core(&GPIO,fgInterruptCore,PIN_FG[i]);
  if(esp_intr_enable(fgInterruptHandle)!=ESP_OK) {
    for(unsigned i=0;i<2;i++)gpio_ll_intr_disable(&GPIO,PIN_FG[i]);
    esp_intr_free(fgInterruptHandle);fgInterruptHandle=nullptr;return false;
  }
  fgInterruptReady=true;return true;
}
