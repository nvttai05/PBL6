#pragma once
#define PERIPH_RCC_ATOMIC() for(bool dataset_test_clock_lock=true; dataset_test_clock_lock; dataset_test_clock_lock=false)
