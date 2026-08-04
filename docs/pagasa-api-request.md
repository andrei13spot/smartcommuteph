# pagasa tenday api access

the engine reads live rainfall from the pagasa tenday forecast api once a token
is configured. access is granted by pagasa through a formal request (their api
doc: tenday.pagasa.dost.gov.ph). until then the engine uses an offline default
of 8mm and the dev dashboard shows the source as "default (no token / offline)".

## how to enable once the token arrives

set the environment variable before starting the engine:

```
set SCPH_PAGASA_TOKEN=your_token_here
```

the engine calls `/api/v1/tenday/current?province=Metro Manila` with the token
header, caches the value for an hour, and falls back to the default if the
network is down.

## request letter draft (send through the university)

> [date]
>
> NATHANIEL T. SERVANDO
> Administrator, PAGASA-DOST
>
> Thru:
> THELMA A. CINCO - Project Leader, CIS4A&H
> MAXIMO F. PERALTA - Chief, Engineering and Technical Services Division
>
> Dear Administrator Servando,
>
> Good day. We are Group 11, fourth-year BS Computer Science students of the
> Polytechnic University of the Philippines, College of Computer and
> Information Sciences. We are respectfully requesting access to the TenDay
> Weather Forecast API for our undergraduate thesis, "ML-Driven Multi-Criteria
> A* for Personalized Route Selection," which uses the ten-day rainfall
> forecast for Metro Manila as the live input to a flood-risk model in a
> commuter routing prototype.
>
> Purpose of API use: academic research (undergraduate thesis prototype);
> rainfall forecast values for Metro Manila feed a Random Forest flood-risk
> model. When and where: [month] to [month] 2026, PUP Sta. Mesa, Manila, and
> the researchers' development machines.
>
> Requesting researcher: [full name], [email], [phone]
>
> We will use the data solely for academic purposes with proper attribution to
> PAGASA-DOST. Thank you for your consideration.
>
> Respectfully,
> [name and signature, Group 11 - BSCS, PUP CCIS]

fill in the bracketed parts, attach their request form, and send it per the
guidelines in their api documentation.
