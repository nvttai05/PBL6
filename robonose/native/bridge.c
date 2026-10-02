/* RoboNose Linux I2C bridge to unmodified Bosch BME68x SensorAPI (BSD-3-Clause).
 * No I2C access occurs until rn_open is explicitly called by hardware backend. */
#define _DEFAULT_SOURCE
#include "vendor/bme68x.h"
#include <linux/i2c.h>
#include <linux/i2c-dev.h>
#include <sys/ioctl.h>
#include <fcntl.h>
#include <unistd.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <stdio.h>

struct context { int fd; unsigned short addr; struct bme68x_dev dev; struct bme68x_conf conf; unsigned int wait_us; };
struct result { double temperature, pressure_pa, humidity, gas_ohm; unsigned char status, index, gas_index, res_heat, idac, gas_wait; };
static int8_t rd(uint8_t reg, uint8_t *data, uint32_t len, void *ptr) {
    struct context *c = ptr;
    struct i2c_msg messages[2] = {{c->addr, 0, 1, &reg}, {c->addr, I2C_M_RD, len, data}};
    struct i2c_rdwr_ioctl_data transfer = {messages, 2};
    return ioctl(c->fd, I2C_RDWR, &transfer) == 2 ? 0 : -1;
}
static int8_t wr(uint8_t reg, const uint8_t *data, uint32_t len, void *ptr) {
    struct context *c = ptr;
    if (len > 255) return -1;
    uint8_t buffer[256]; buffer[0] = reg; memcpy(buffer + 1, data, len);
    struct i2c_msg message = {c->addr, 0, len + 1, buffer};
    struct i2c_rdwr_ioctl_data transfer = {&message, 1};
    return ioctl(c->fd, I2C_RDWR, &transfer) == 1 ? 0 : -1;
}
static void delay(uint32_t us, void *ptr) { (void)ptr; usleep(us); }
void rn_close(void *ptr) {
    struct context *c = ptr;
    if (c) { close(c->fd); free(c); }
}
void *rn_open(int bus, int addr, int *code) {
    struct context *c = calloc(1, sizeof(*c));
    if (!c) { *code = -100; return NULL; }
    char path[64]; snprintf(path, sizeof(path), "/dev/i2c-%d", bus);
    c->fd = open(path, O_RDWR | O_CLOEXEC);
    if (c->fd < 0) { *code = -1000 - errno; free(c); return NULL; }
    c->addr = addr; c->dev.intf_ptr = c; c->dev.intf = BME68X_I2C_INTF;
    c->dev.read = rd; c->dev.write = wr; c->dev.delay_us = delay; c->dev.amb_temp = 25;
    *code = bme68x_init(&c->dev);
    if (!*code && c->dev.variant_id != BME68X_VARIANT_GAS_HIGH) *code = -101;
    if (*code) { rn_close(c); return NULL; }
    return c;
}
int rn_config(void *ptr, int temp_os, int hum_os, int pres_os, int heater_c, int heater_ms) {
    struct context *c = ptr;
    struct bme68x_conf cfg = {0};
    cfg.os_temp = temp_os; cfg.os_hum = hum_os; cfg.os_pres = pres_os;
    cfg.filter = BME68X_FILTER_OFF; cfg.odr = BME68X_ODR_NONE;
    int r = bme68x_set_conf(&cfg, &c->dev);
    if (r) return r;
    r = bme68x_get_conf(&c->conf, &c->dev);
    if (r) return r;
    if (c->conf.os_temp != temp_os || c->conf.os_hum != hum_os || c->conf.os_pres != pres_os) return -102;
    struct bme68x_heatr_conf heater = {0};
    heater.enable = BME68X_ENABLE; heater.heatr_temp = heater_c; heater.heatr_dur = heater_ms;
    r = bme68x_set_heatr_conf(BME68X_FORCED_MODE, &heater, &c->dev);
    if (r) return r;
    /* Register encodes quantized heater duration; read it back for applied metadata. */
    uint8_t gw;
    r = bme68x_get_regs(BME68X_REG_GAS_WAIT0, &gw, 1, &c->dev);
    if (r) return r;
    uint32_t actual_ms = (gw & 63) * (1U << (2 * (gw >> 6)));
    c->wait_us = bme68x_get_meas_dur(BME68X_FORCED_MODE, &c->conf, &c->dev) + actual_ms * 1000 + 1000;
    return 0;
}
int rn_info(void *ptr, int *output) {
    struct context *c = ptr;
    uint8_t regs[2];
    int r = bme68x_get_regs(BME68X_REG_RES_HEAT0, regs, 1, &c->dev);
    if (r) return r;
    r = bme68x_get_regs(BME68X_REG_GAS_WAIT0, regs + 1, 1, &c->dev);
    if (r) return r;
    output[0] = c->dev.chip_id; output[1] = c->dev.variant_id;
    output[2] = regs[0]; output[3] = regs[1]; output[4] = c->wait_us;
    return 0;
}
int rn_read(void *ptr, struct result *output) {
    struct context *c = ptr;
    int r = bme68x_set_op_mode(BME68X_FORCED_MODE, &c->dev);
    if (r) return r;
    delay(c->wait_us, c);
    struct bme68x_data data = {0}; uint8_t n = 0;
    r = bme68x_get_data(BME68X_FORCED_MODE, &data, &n, &c->dev);
    if (r) return r;
    if (!n) return BME68X_W_NO_NEW_DATA;
    output->temperature = data.temperature; output->pressure_pa = data.pressure;
    output->humidity = data.humidity; output->gas_ohm = data.gas_resistance;
    output->status = data.status; output->index = data.meas_index; output->gas_index = data.gas_index;
    output->res_heat = data.res_heat; output->idac = data.idac; output->gas_wait = data.gas_wait;
    return 0;
}
