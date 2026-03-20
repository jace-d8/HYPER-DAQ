from lakeshore import Model336

# Detect interface & connect
my_instrument = Model336() # serial, com port , buad, data, stop, parity
#
# Print the temperature of Input A in Kelvin
while True:
    temperature_A = my_instrument.get_kelvin_reading("A")
    print(f"Temperature at Input A: {temperature_A} K")


# now:
# what interval?