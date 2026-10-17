# Judges ke liye presentation script (Hinglish)

Total time lagbhag 7 se 8 minute. Har hisse mein likha hai ki bolte waqt screen par kya dikhana hai.

---

## 1. Shuruaat (30 second)
*Screen: Homepage, train station 1 par khadi.*

> "Namaste sir/ma'am. Hamari team ka project hai **AI-Powered Automatic Block Planning**, Smart India Hackathon 2026, Problem Statement 26027.
>
> Hum aapko 7 minute mein dikhayenge ki problem kya hai, hum kaise solve karte hain, aur result kya aaya."

---

## 2. Problem (1 minute)
*Screen: Homepage, scroll karke station 1 "Request" par.*

> "Railway mein track ki maintenance ke liye **block** lena padta hai. Block ka matlab hai ki track ka ek hissa kuch ghante ke liye band kar diya jaata hai, taaki engineers kaam kar sakein.
>
> Problem yeh hai ki teen department alag-alag block maangte hain:
> - **Engineering**, track ke liye.
> - **TrD (Traction Distribution)**, overhead bijli ke taar ke liye.
> - **S&T (Signal and Telecom)**, signal ke liye.
>
> Ye teeno apni-apni request alag se dete hain. Natija yeh hota hai ki **ek hi section baar-baar band hota hai**, jabki teeno kaam ek hi baar mein ho sakte the. Isse trains zyada late hoti hain aur track ka time barbaad hota hai."

---

## 3. Hamara solution (1 minute)

> "Hamara system teeno departments ki requests ek saath leta hai aur **ek hi plan** banata hai. Jo kaam ek hi section par hain, unhe ek hi closure window mein rakhta hai. Aur woh window aise time par rakhta hai jab **trains kam chalti hain**.
>
> Sabse zaroori baat: **system sirf suggest karta hai, faisla insaan karta hai.** Planner plan dekhta hai, reasons dekhta hai, badlav kar sakta hai, aur tabhi approve aur publish karta hai."

> "Ek zaroori baat pehle hi bata dein: is project ka **saara data synthetic (nakli) hai.** Timetable, traffic aur requests humne khud banaye hain. Asli railway data hamare paas nahi tha, aur yeh system asli trains ko control nahi karta."

---

## 4. Live demo (3 minute)

### Step 1: Requests (30 second)
*Screen: Login karke Requests page.*

> "Yeh Requests page hai. Yahan 16 block requests hain, teeno departments ki. Har request mein section, kaam ki kism, kitne ghante, kis date window mein, aur priority hai.
>
> Dhyan dijiye, kuch requests ki **dependency** hai. Jaise R5 aur R6 tabhi shuru ho sakti hain jab R1 khatam ho jaaye. System dependency mein **cycle** nahi banne deta, yaani A, B ka intezaar kare aur B, A ka."

### Step 2: Plan chalana (45 second)
*Screen: Plans page. Date 19 Oct, time limit 20 se 30 second, Run plan dabayein.*

> "Ab planner **Run plan** dabata hai. Peeche background mein hamara optimizer chalta hai. Yeh Google ka **OR-Tools CP-SAT solver** hai. Page har 2 second mein khud status check karta hai.
>
> Solver in sab rules ko ek saath dekhta hai:
> - Ek hi section aur ek hi din ke kaam ek closure share kar sakte hain.
> - Har department ke paas sirf 2 crew hain.
> - Dependencies ka order sahi rehna chahiye.
> - Closure kam se kam ho, aur wahan ho jahan trains kam hon."

### Step 3: Result (1 minute)
*Screen: Dashboard.*

> "Yeh result hai. Pehle hamne **independent planning** ki, yaani har department apne aap. Phir **integrated plan** banaya, yaani sab saath mein. Hamare run mein:
>
> | | Independent | Integrated |
> |---|---|---|
> | Closures | 15 | 7 |
> | Block hours | 35 | 24 |
> | Trains affected | 56 | 12 |
>
> Closures **53% kam**, block hours **31% kam**, aur prabhavit trains **79% kam**. Teeno ka average sudhaar **54%** hai.
>
> Yeh numbers har run mein thode alag aa sakte hain, kyunki solver time limit par ruk jaata hai. Aur yaad rakhiye, yeh synthetic data par hain. Yeh asli railway ke performance ka daava nahi hai."

### Step 4: Schedule aur reasons (45 second)
*Screen: Plan detail, Gantt, phir Explanations.*

> "Yeh Gantt chart hai. Har row ek section hai, har bar ek closure, aur rang department ke hisaab se hain. Bar par mouse le jaane par pata chalta hai ki kaun si requests ek saath hain.
>
> **Explanations** tab mein har decision ka **reason aur uske peeche ke numbers** hain. Hamara maanna hai ki jo AI apne decision ki wajah na bataye, uspar planner bharosa nahi karega."

### Step 5: What-if, Approve, Publish (30 second)
*Screen: What-if, phir Approve, Publish, phir Calendar.*

> "Planner kisi request ko doosre time par move karke **what-if** dekh sakta hai. Isse kuch save nahi hota, bas farak dikhta hai. **Override** karne par ek naya child plan banta hai, purana plan safe rehta hai.
>
> Approve aur Publish dono ke liye confirmation aata hai. Publish hone ke baad closures **Calendar** mein section aur din ke hisaab se dikhte hain. Publish ke waqt system check karta hai ki ek hi section par do closure overlap na karein."

---

## 5. Technology (1 minute)

> "Technology ki baat karein toh:
> - **Backend:** Python, FastAPI aur SQLite. Docker ya Redis ki zaroorat nahi, ek laptop par chalta hai.
> - **Optimizer:** OR-Tools CP-SAT.
> - **Frontend:** React, TypeScript aur Vite.
> - **Security:** password argon2id se hash hote hain, login JWT tokens se hota hai, aur chaar roles hain: admin, planner, department user aur viewer.
>
> Hamne **machine learning** bhi use ki hai: ek delay model jo batata hai ki closure se kitne train-minutes barbaad honge. Yeh simple train ginti se tab hi behtar maana jaata hai jab test data par baseline ko kam se kam 2% se haraye. Agar model nahi mile ya fail ho jaaye, toh planner apne aap train ginti par wapas aa jaata hai."

---

## 6. Quality aur imaandari (45 second)

> "Hamne yeh bhi dhyan rakha ki hum jo kahein, woh sach ho:
> - Har plan save hone se pehle ek **alag checker** se guzarta hai.
> - Backend ke **601 tests**, frontend ke **148 tests**, aur ek real-browser check, sab pass hue.
> - Sab kuch **SQLite** par test hua hai. **Postgres aur Docker par hamne kabhi nahi chalaya.**
> - Abhi 200 se zyada requests ke liye solver ko todne ka kaam nahi hua hai.
> - Overrun model train hota hai, lekin planner abhi use nahi karta.
>
> Yeh sab README ke Limitations section mein likha hai."

---

## 7. Samapti (20 second)

> "Sankshep mein: teen department ki alag-alag requests ko ek hi plan mein jodkar hum closures aur trains ki deri kam karte hain, aur har decision ka reason dikhate hain. Planner ke haath mein hi aakhri faisla rehta hai.
>
> Dhanyavaad. Ab hum aapke sawaalon ka jawaab dene ke liye taiyaar hain."

---

## Judges ke possible sawaal aur jawaab

**1. Data asli hai kya?**
> "Nahi, sab synthetic hai. Asli railway data hamare paas nahi tha. Hamne timetable aur traffic generate kiya aur apni assumptions saaf likhi hain."

**2. Solver ko optimal answer milta hai ya sirf achha?**
> "Solver time limit par ruk jaata hai, isliye hamesha proved optimal nahi hota. System yeh bhi honestly report karta hai ki optimum prove hua ya nahi."

**3. Agar solver crash ho jaaye toh?**
> "Solver ek alag process mein chalta hai. Crash hone par sirf wahi plan run fail hota hai, server nahi girta. Plan hamesha ek valid greedy plan se shuru hota hai."

**4. ML model asli kaam karta hai ya sirf dikhane ke liye?**
> "Model synthetic data par train hua hai, jisme hidden pattern humne khud likha hai. Isliye baseline se behtar aana sirf yeh dikhata hai ki pipeline sahi hai, asli railway ka saboot nahi. Asli data milne par wahi pipeline dobara train hogi."

**5. Scale kitna ho sakta hai?**
> "Humne 200 requests tak benchmark kiya hai, naya result README mein hai. Usse bade size ke liye solver ko hisson mein todna hoga, jo abhi nahi hua."

**6. Yeh asli railway mein kaise use hoga?**
> "Yeh sirf proposal banata hai, aur koi insaan approve karta hai. Asli deployment ke liye asli timetable, power block aur resource data jodna padega. Yeh humare Future Work mein hai."

---

## Presentation ke liye tips
- Demo se pehle ek baar plan chala kar rakhein, taaki Dashboard mein numbers pehle se hon. Live run mein 20 se 30 second lagte hain.
- Numbers ek baar apni screen se dekh lein. Upar ki table ek run (7, 24, 12) ki hai, aur README ke example mein 10, 24, 17 hain.
- Agar kuch fail ho jaaye toh bolein "yeh Known issues mein hai", aur aage badhein.
