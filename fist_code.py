import date
import random
import 

kali = 0 
bali = 0
saki = 0 
kaki = 0 



print("                 Q1. what is different between kali and bali ?                  ")
print("                 (1) kali is big and bali is small                             ")
print("                 (2)   kali is small and bali is big                           ")

answer = int(input("enter your answer (1 or 2): "))



if answer == 2:
    kali += 1
    bali += 1
    print("correct answer   ")
if answer == 1:
    saki -= 1
    kaki -= 1
    print("wrong answer   ")

    print("kali score is :", kali)
    print("bali score is :", bali)
    print("saki score is :", saki)
    print("kaki score is :", kaki)

    def advance():
        print("you have unlocked advance level")
        print("                  Q2. what is different between saki and kaki ?                  ")
        print("                 (1) saki is round and kaki is long                             ")
        print("                 (2)   saki is long and kaki is round                           ")

        answer = int(input("enter your answer (1 or 2): "))
        if answer == 1:
            saki += 1
            kaki += 1
            print("correct answer   ")
        if answer == 2:
            saki -= 1
            kaki -= 1
            print("wrong answer   ")

    advance()

print("kali score is :", kali)
print("bali score is :", bali)      
print("saki score is :", saki)
print("kaki score is :", kaki)

def logs():
    rand.randint(1,19999)
