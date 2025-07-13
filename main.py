#counting app

print("Welcome to the ICF finance app")

print("press: ")
print("1. for offering calculations")
print("2. to exit")
while True:
    try:
        user = int(input("Type here: "))
        break
    except:
        print("Please type in numbers only")

VAL_ONECENTCOIN = 0.01
VAL_TWOCENTCOIN = 0.02
VAL_FIVECENTCOIN = 0.05
VAL_TENCENTCOIN = 0.10
VAL_TWENTYCENTCOIN = 0.20
VAL_FIFTYCENTCOIN = 0.50
VAL_TWOEUROSCOIN = 2
VAL_ONEEUROCOIN = 1
VAL_FIVEEUROBILL = 5
VAL_TENEUROBILL = 10
VAL_TWENTYEUROBILL = 20
VAL_FIFTYEUROBILL = 50
VAL_HUNDREDEUROBILL = 100

total = 0



userDone = False


if user == 1:

    while(userDone != True):
        while True:
            try:
                print("Write the value of the bill/coin. Ex: 0.50 for 50 cents, 1 for 1 euro bill, 5 for 5 euro bill and so on")
                amount = float(input("write the currency coins/bills you want to count: "))
                value = float(input(f"Type how many of {amount} here: "))
                break
            except:
                print("Please only type numbers")


        total += amount * value
        while True:
            try:
                print("Do you want to you want to continue calculating? ")
                print("1. yes")
                print("2. no")
                user_continue = int(input("Type here: "))
                break
            except:
                print("Please only type 1 or 2 for these options")

        if user_continue == 1:
            continue
        elif user_continue == 2:
            print(f"Ok your total is ${total}")
            userDone = True



