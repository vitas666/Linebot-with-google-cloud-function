from datetime import date, timedelta, datetime

def allSundays(year):
   d = date(year, 1, 1)                    # January 1st
   d += timedelta(days = 6 - d.weekday())  # First Sunday
   while d.year == year:
      yield d
      d += timedelta(days = 7)
      
def allSaturdays(year):
   d = date(year, 1, 1)                    # January 1st
   d += timedelta(days = 5 - d.weekday())  # First Saturday
   while d.year == year:
      yield d
      d += timedelta(days = 7)

def lastSaturday(reference_date):
    # Calculate how many days to subtract to get to the last Saturday
    days_to_subtract = (reference_date.weekday() - 5) % 7
    # Subtract the days from the reference date
    last_saturday = reference_date - timedelta(days=days_to_subtract)
    return last_saturday.strftime('%Y-%m-%d')

def lastSunday(reference_date):
    # Calculate how many days to subtract to get to the last Saturday
    days_to_subtract = (reference_date.weekday() - 6) % 7
    # Subtract the days from the reference date
    last_saturday = reference_date - timedelta(days=days_to_subtract)
    return last_saturday.strftime('%Y-%m-%d')
 
