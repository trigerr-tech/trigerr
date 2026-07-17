from trigerr.data.historical import *
from trigerr.custom_indicators import *
import datetime
import math
import itertools
import traceback as tb
import requests
from trigerr import ta as TA
from urllib.parse import urljoin

orders_url = config.get('orders_url')


def get_symbol_details(db_cursor, symbol, market="IN"):
    """ Function to load and get symbols dict """
    try:
        symbol_dict = db_cursor['all_symbols'].find_one({"name": symbol, "market": market})
        if symbol_dict:
            return symbol_dict
        else:
            print("No Such Symbol Found")
            return None
    except Exception as e:
        print(f"Exception in Getting Symbols Dict : {e}")
        return None


def change_granularity(data_df, granularity):
    """ Function to Change Granularity for Provided Dataframe """
    try:
        data_df['timestamp'] = pd.to_datetime(data_df['timestamp'])
        if 'date' in data_df.columns:
            data_df['date'] = pd.to_datetime(data_df['date'])

        if 'symbol' in data_df.columns:
            symbols = sorted(set(data_df['symbol']))
        else:
            symbols = [""]

        final_data_li = list()

        def create_row_dict(gran_calc_list):
            open_ = gran_calc_list[0]['open']
            close_ = gran_calc_list[-1]['close']
            high_ = max(gran_calc_list, key=lambda x: x['high'])['high']
            low_ = min(gran_calc_list, key=lambda x: x['low'])['low']
            timestamp_ = gran_calc_list[0]['timestamp']

            row_dict = {'open': open_, 'high': high_, 'low': low_, 'close': close_,
                        'timestamp': timestamp_}

            if 'oi' in gran_calc_list[-1]:
                row_dict['oi'] = sum([i["oi"] for i in gran_calc_list])
            if 'volume' in gran_calc_list[-1]:
                row_dict['volume'] = sum([i["volume"] for i in gran_calc_list])
            if 'previous_day_close' in gran_calc_list[0]:
                row_dict['previous_day_close'] = gran_calc_list[0]['previous_day_close']
            if 'curr_day_open' in gran_calc_list[0]:
                row_dict['curr_day_open'] = gran_calc_list[0]['curr_day_open']
            if 'symbol' in gran_calc_list[0]:
                row_dict['symbol'] = gran_calc_list[0]['symbol']
            if 'date' in gran_calc_list[0]:
                row_dict['date'] = gran_calc_list[0]['date']
            if 'underlying_stock' in gran_calc_list[0]:
                row_dict['underlying_stock'] = gran_calc_list[0]['underlying_stock']
            if 'strike' in gran_calc_list[0]:
                row_dict['strike'] = gran_calc_list[0]['strike']
            if 'option_type' in gran_calc_list[0]:
                row_dict['option_type'] = gran_calc_list[0]['option_type']
            if 'expiry' in gran_calc_list[0]:
                row_dict['expiry'] = gran_calc_list[0]['expiry']

            return row_dict

        for symbol in symbols:
            if symbol != 0:
                sym_data_df = data_df[data_df['symbol'] == symbol]
            else:
                sym_data_df = data_df

            # sym_data_df = sym_data_df.sort_values('timestamp', inplace=True)
            sorted_sym_data_df = sym_data_df.sort_values('timestamp')

            data_li = sorted_sym_data_df.to_dict('records')

            st_time = data_li[0]['timestamp'].time()

            gran_rows = list()
            gran_calc_list = list()

            for row in data_li:
                if row['timestamp'].time() == st_time:
                    if gran_calc_list:
                        row_dict = create_row_dict(gran_calc_list)

                        gran_rows.append(row_dict)

                    gran_calc_list = list()

                gran_calc_list.append(row)

                if len(gran_calc_list) == granularity:
                    row_dict = create_row_dict(gran_calc_list)

                    gran_rows.append(row_dict)
                    gran_calc_list = list()

            if gran_calc_list:
                row_dict = create_row_dict(gran_calc_list)

                gran_rows.append(row_dict)

            new_df = pd.DataFrame(gran_rows)
            new_df.dropna(subset=['close'], inplace=True)
            final_data_li.extend(new_df.to_dict('records'))

        final_df = pd.DataFrame(final_data_li)

    except Exception as e:
        final_df = data_df
        log_message = f"Exception in changing the granularity of provided dataframe.\nReturning the same dataframe\n{e}\n"
        print(log_message)

    return final_df


def calculate_swing(df, swing_setup=2, ignore_last_bar=False):
    """ Function to calculate swing """

    def func_upswing():
        """ Checks up swing continuation conditions """

        nonlocal data, horizontal_line, prev_candle, current_candle, swings, outside_bars, prev_idx, current_idx, p_hlines, p_swings

        try:
            _outsidebar_hh_ = max(*data[data.index(horizontal_line): current_idx], horizontal_line,
                                  key=lambda bar: bar['High'])
        except:
            _outsidebar_hh_ = swings[-1][0]

        # If Outside bar and curr_candle makes highest of high and close below prev_candle low then convert to up swing
        if (current_candle['High'] > prev_candle['High'] and current_candle['Low'] < prev_candle['Low']) and \
                (current_candle['Close'] < prev_candle['Low']) and (current_candle['High'] > _outsidebar_hh_['High']):
            p_hlines.append([horizontal_line, data[data.index(horizontal_line) + 1], "DOWN"])
            try:
                p_swings.append(
                    [max(*data[data.index(horizontal_line): current_idx + 1], horizontal_line,
                         key=lambda bar: bar['High']), "DOWN"])
            except:
                pass
            outside_bars.append([current_candle, "DOWN"])
            swings.append([current_candle, "DOWN"])
            horizontal_line = max(data[prev_idx - swing_setup: current_idx + 1], key=lambda bar: bar['High'])
            return horizontal_line, "DOWN"

        # Check swing break means down swing starts
        if current_candle['Close'] < horizontal_line['Low']:
            p_hlines.append([horizontal_line, data[data.index(horizontal_line) + 1], "DOWN"])
            try:
                p_swings.append(
                    [max(*data[data.index(horizontal_line): current_idx + 1], horizontal_line,
                         key=lambda bar: bar['High']), "DOWN"])
            except:
                pass

            swings.append([current_candle, "DOWN"])
            horizontal_line = max(data[prev_idx - swing_setup: current_idx + 1], key=lambda bar: bar['High'])
            return horizontal_line, "DOWN"

        # Check is there any upswing shift
        if current_candle['High'] > swings[-1][0]['High']:
            swings.append([current_candle, "UP"])
            horizontal_line = min(data[prev_idx - swing_setup: current_idx + 1], key=lambda bar: bar['Low'])
            return horizontal_line, "UP"

        # Return Up swing continues because no condition met, swing just rolling
        return horizontal_line, "UP"

    def func_downswing():
        """ Checks down swing continuation conditions """

        nonlocal data, horizontal_line, prev_candle, current_candle, swings, outside_bars, prev_idx, current_idx, p_hlines, p_swings

        try:
            _outsidebar_ll_ = min(*data[data.index(horizontal_line): current_idx], horizontal_line,
                                  key=lambda bar: bar['Low'])
        except:
            _outsidebar_ll_ = swings[-1][0]

        # If Outside bar and curr_candle makes lowest of low and close above prev_candle high then convert to up swing
        if (current_candle['High'] > prev_candle['High'] and current_candle['Low'] < prev_candle['Low']) and \
                (current_candle['Close'] > prev_candle['High']) and (current_candle['Low'] < _outsidebar_ll_['Low']):
            p_hlines.append([horizontal_line, data[data.index(horizontal_line) + 1], "UP"])
            try:
                p_swings.append(
                    [min(*data[data.index(horizontal_line): current_idx + 1], horizontal_line,
                         key=lambda bar: bar['Low']), "UP"])
            except:
                pass
            outside_bars.append([current_candle, "UP"])
            swings.append([current_candle, "UP"])
            horizontal_line = min(data[prev_idx - swing_setup: current_idx + 1], key=lambda bar: bar['Low'])
            return horizontal_line, "UP"

        # Check swing break means up swing starts
        if current_candle['Close'] > horizontal_line['High']:
            p_hlines.append([horizontal_line, data[data.index(horizontal_line) + 1], "UP"])
            try:
                p_swings.append([min(*data[data.index(horizontal_line): current_idx + 1], horizontal_line, key=lambda bar: bar['Low']), "UP"])
            except Exception as e:
                print("exception here : {}".format(e))
                pass

            swings.append([current_candle, "UP"])
            horizontal_line = min(data[prev_idx - swing_setup: current_idx + 1], key=lambda bar: bar['Low'])
            return horizontal_line, "UP"

        # Check is there any downswing shift
        if current_candle['Low'] < swings[-1][0]['Low']:
            swings.append([current_candle, 'DOWN'])
            horizontal_line = max(data[prev_idx - swing_setup: current_idx + 1], key=lambda bar: bar['High'])
            return horizontal_line, "DOWN"

        # Return Down swing continues because no condition met, swing just rolling
        return horizontal_line, "DOWN"

    def func_check_swing_chg():
        if len(swings) >= 2:
            if swings[-2][-1] != swings[-1][-1] and swings[-1][0]['timestamp'] == current_candle['timestamp']:
                return True
        return False

    try:
        # Initialization
        swing_setup -= 2
        prev_idx = 0
        current_idx = 1
        horizontal_line = ""
        current_swing_type = ""
        swings = []
        p_hlines = []
        p_swings = []
        outside_bars = []

        # Formatting data
        df.reset_index(inplace=True)
        df.rename({"datetime": "timestamp", "open": "Open", "high": "High", "low": "Low", "close": "Close"}, axis=1,
                  inplace=True)
        df['swing'], df['swing_change'] = '', False

        # Avoiding current day bar because its not completely build [Keep `False` while backtesting only]
        if ignore_last_bar:
            df = df.iloc[:-1, :]

        data = df.to_dict('index')
        data = [data[i] for i in sorted(list(data.keys()))]

        # Start Swing creation
        while current_idx < (len(data)):
            prev_candle = data[prev_idx]
            current_candle = data[current_idx]
            # Wait till minimum bars built
            if prev_idx <= swing_setup:
                prev_idx += 1
                current_idx += 1
                continue

            ##################################################
            # Swing Initialization
            if horizontal_line == "":
                horizontal_line = prev_candle
                upside_horizontal_line = max(data[prev_idx - swing_setup: prev_idx + 1], key=lambda x: x['High'])
                downside_horizontal_line = min(data[prev_idx - swing_setup: prev_idx + 1], key=lambda x: x['Low'])

            if current_swing_type == "":
                if current_candle['Close'] > horizontal_line['High']:
                    swings.append([upside_horizontal_line, "UP"])
                    horizontal_line = min(data[prev_idx - swing_setup: current_idx + 1], key=lambda bar: bar['Low'])
                    current_swing_type = "UP"
                elif current_candle['Close'] < horizontal_line['Low']:
                    swings.append([downside_horizontal_line, "DOWN"])
                    horizontal_line = max(data[prev_idx - swing_setup: current_idx + 1], key=lambda bar: bar['High'])
                    current_swing_type = "DOWN"
            ##################################################

            # Continue Swing building
            if current_swing_type == "UP":
                # Continue loop till swing change
                while current_swing_type != "DOWN":
                    if horizontal_line != current_candle:
                        horizontal_line, current_swing_type = func_upswing()

                    # Update df
                    df.loc[current_idx, 'swing'] = current_swing_type
                    df.loc[current_idx, 'swing_change'] = func_check_swing_chg()

                    prev_idx += 1
                    current_idx += 1

                    # Checking whether the last candle is current candle
                    if len(data) == current_idx:
                        break
                    else:
                        prev_candle = data[prev_idx]
                        current_candle = data[current_idx]

            elif current_swing_type == "DOWN":
                # Continue loop till swing change
                while current_swing_type != "UP":
                    if horizontal_line != current_candle:
                        horizontal_line, current_swing_type = func_downswing()

                    # Update df
                    df.loc[current_idx, 'swing'] = current_swing_type
                    df.loc[current_idx, 'swing_change'] = func_check_swing_chg()

                    prev_idx += 1
                    current_idx += 1

                    if len(data) == current_idx:
                        break
                    else:
                        prev_candle = data[prev_idx]
                        current_candle = data[current_idx]
            else:
                prev_idx += 1
                current_idx += 1
        df.rename({"datetime": "timestamp", "Open": "open", "High": "high", "Low": "low", "Close": "close"}, axis=1,
                  inplace=True)
        return df
    except Exception as e:
        print("Exception in Swing Calculation : {}".format(e))
        return df


def calculate_rolling_swing(df):
    """ Function to calculate Rolling Swing """
    try:
        print("Calculating Rolling Swing")
        swing_list = []
        candles = df.to_dict('records')
        last_swing = None
        for indx, candle in enumerate(candles):
            if indx >= 2:
                prev_candle_1 = candles[indx - 1]
                prev_candle_2 = candles[indx - 2]

                # Conditions for Upswing
                up_condition = candle["open"] > prev_candle_1["close"] and candle["open"] > prev_candle_2["close"]

                # Conditions for DownSwing
                down_condition = candle["open"] < prev_candle_1["close"] and candle["open"] < prev_candle_2["close"]

                if up_condition:
                    current_swing = "UP"
                    if current_swing != last_swing:
                        last_swing = "UP"
                        swing_change = True
                    else:
                        swing_change = False

                elif down_condition:
                    current_swing = "DOWN"
                    if current_swing != last_swing:
                        last_swing = "DOWN"
                        swing_change = True
                    else:
                        swing_change = False
                else:
                    swing_change = False
                    current_swing = last_swing

                candle["swing"] = current_swing
                candle["swing_change"] = swing_change

                swing_list.append(candle)
            else:
                candle["swing"] = None
                candle["swing_change"] = False
                swing_list.append(candle)

        # Converting Swings Candles list to Dataframe
        swing_df = pd.DataFrame(swing_list)
        return swing_df
    except Exception as e:
        print("Exception in calculating rolling swing : {}".format(e))
        pass


def apply_indicators(dataframe, indicators_dict):
    """ Function to apply indicators on the dataframe provided """
    try:

        if "ATR" in indicators_dict:
            atr_values = TA.atr(dataframe['high'], dataframe['low'], dataframe['close'], length=indicators_dict["ATR"]["length"],
                                mamode=indicators_dict["ATR"]["mamode"])
            atr_values = round(atr_values, 2).fillna(0)
            dataframe["atr"] = atr_values.values.tolist()

        if "ADX" in indicators_dict:
            adx_values = TA.adx(high=dataframe['high'], low=dataframe['low'], close=dataframe['close'], length=indicators_dict["ADX"]["length"],
                                lensig=indicators_dict["ADX"]["lensig"])
            dataframe["adx"] = round(adx_values.iloc[:, 0], 2).fillna(0).values
            dataframe["adx_dmp"] = round(adx_values.iloc[:, 1], 2).fillna(0).values
            dataframe["adx_dmn"] = round(adx_values.iloc[:, 2], 2).fillna(0).values

        if "EMA" in indicators_dict:
            ema_values = TA.ema(dataframe["close"], length=indicators_dict["EMA"]["length"])
            ema_values = round(ema_values, 2).fillna(0)
            dataframe["ema"] = ema_values.values.tolist()

        if "EMA5" in indicators_dict:
            input_series = dataframe["close"]

            if indicators_dict["EMA5"]["source"] == "close":
                input_series = dataframe["close"]

            elif indicators_dict["EMA5"]["source"] == "open":
                input_series = dataframe["open"]

            elif indicators_dict["EMA5"]["source"] == "ohlc4":
                input_series = (dataframe["open"] + dataframe['high'] + dataframe["low"] + dataframe["close"])/4

            elif indicators_dict["EMA5"]["source"] == "hlc3":
                input_series = (dataframe['high'] + dataframe["low"] + dataframe["close"])/3

            ema5_values = TA.ema(input_series, length=indicators_dict["EMA5"]["length"])
            ema5_values = round(ema5_values, 2).fillna(0)
            dataframe["ema5"] = ema5_values.values.tolist()

        if "EMA6" in indicators_dict:
            input_series = dataframe["close"]

            if indicators_dict["EMA5"]["source"] == "close":
                input_series = dataframe["close"]

            elif indicators_dict["EMA5"]["source"] == "open":
                input_series = dataframe["open"]

            elif indicators_dict["EMA5"]["source"] == "ohlc4":
                input_series = (dataframe["open"] + dataframe['high'] + dataframe["low"] + dataframe["close"]) / 4

            elif indicators_dict["EMA5"]["source"] == "hlc3":
                input_series = (dataframe['high'] + dataframe["low"] + dataframe["close"]) / 3

            ema6_values = TA.ema(input_series, length=indicators_dict["EMA6"]["length"])
            ema6_values = round(ema6_values, 2).fillna(0)
            dataframe["ema6"] = ema6_values.values.tolist()

        if "EMA9" in indicators_dict:
            ema9_values = TA.ema(dataframe["close"], length=indicators_dict["EMA9"]["length"])
            # ema9_values = round(ema9_values, 2).fillna(0)
            ema9_values = ema9_values.fillna(0)
            dataframe["ema9"] = ema9_values.values.tolist()

        if "EMA14" in indicators_dict:
            ema14_values = TA.ema(dataframe["close"], length=indicators_dict["EMA14"]["length"])
            ema14_values = round(ema14_values, 2).fillna(0)
            dataframe["ema14"] = ema14_values.values.tolist()

        if "EMA15" in indicators_dict:
            ema15_values = TA.ema(dataframe["close"], length=indicators_dict["EMA15"]["length"])
            ema15_values = round(ema15_values, 2).fillna(0)
            dataframe["ema15"] = ema15_values.values.tolist()

        if "EMA20" in indicators_dict:
            ema20_values = TA.ema(dataframe["close"], length=indicators_dict["EMA20"]["length"])
            # ema20_values = round(ema20_values, 2).fillna(0)
            ema20_values = ema20_values.fillna(0)
            dataframe["ema20"] = ema20_values.values.tolist()

        if "EMA50" in indicators_dict:
            ema50_values = TA.ema(dataframe["close"], length=indicators_dict["EMA50"]["length"])
            ema50_values = round(ema50_values, 2).fillna(0)
            dataframe["ema50"] = ema50_values.values.tolist()

        if "EMA60" in indicators_dict:
            ema60_values = TA.ema(dataframe["close"], length=indicators_dict["EMA60"]["length"])
            ema60_values = round(ema60_values, 2).fillna(0)
            dataframe["ema60"] = ema60_values.values.tolist()

        if "EMA200" in indicators_dict:
            ema200_values = TA.ema(dataframe["close"], length=indicators_dict["EMA200"]["length"])
            ema200_values = round(ema200_values.fillna(0), 2)
            dataframe["ema200"] = ema200_values.values.tolist()

        if "SMA" in indicators_dict:
            sma_values = TA.sma(dataframe["close"], length=indicators_dict["SMA"]["length"])
            sma_values = round(sma_values, 2).fillna(0)
            dataframe["sma"] = sma_values.values.tolist()

        if "SMA5" in indicators_dict:
            sma_values = TA.sma(dataframe["close"], length=indicators_dict["SMA5"]["length"])
            sma_values = round(sma_values, 2).fillna(0)
            dataframe["sma5"] = sma_values.values.tolist()

        if "SMA9" in indicators_dict:
            sma_values = TA.sma(dataframe["close"], length=indicators_dict["SMA9"]["length"])
            sma_values = round(sma_values, 2).fillna(0)
            dataframe["sma9"] = sma_values.values.tolist()

        if "SMA15" in indicators_dict:
            sma_values = TA.sma(dataframe["close"], length=indicators_dict["SMA15"]["length"])
            sma_values = round(sma_values, 2).fillna(0)
            dataframe["sma15"] = sma_values.values.tolist()

        if "SMA13" in indicators_dict:
            sma_values = TA.sma(dataframe["close"], length=indicators_dict["SMA13"]["length"])
            sma_values = round(sma_values, 2).fillna(0)
            dataframe["sma13"] = sma_values.values.tolist()

        if "SMA34" in indicators_dict:
            sma_values = TA.sma(dataframe["close"], length=indicators_dict["SMA34"]["length"])
            sma_values = round(sma_values, 2).fillna(0)
            dataframe["sma34"] = sma_values.values.tolist()

        if "SMA20" in indicators_dict:
            sma_values = TA.sma(dataframe["close"], length=indicators_dict["SMA20"]["length"])
            sma_values = round(sma_values, 2).fillna(0)
            dataframe["sma20"] = sma_values.values.tolist()

        if "SMA50" in indicators_dict:
            sma_values = TA.sma(dataframe["close"], length=indicators_dict["SMA50"]["length"])
            sma_values = round(sma_values, 2).fillna(0)
            dataframe["sma50"] = sma_values.values.tolist()

        if "SMA200" in indicators_dict:
            sma_values = TA.sma(dataframe["close"], length=indicators_dict["SMA200"]["length"])
            if sma_values is not None:
                sma_values = round(sma_values, 2).fillna(0)
                dataframe["sma200"] = sma_values.values.tolist()
            else:
                dataframe["sma200"] = 0

        if "ECR" in indicators_dict:
            ecr_values = dataframe["ema"] - dataframe["ema70"]
            ecr_values = round(ecr_values, 2).fillna(0)
            dataframe["ecr"] = ecr_values.tolist()

        if "STOCH" in indicators_dict:
            stoch_df = stochastic_oscillator(dataframe=dataframe, k=indicators_dict["STOCH"]["k"], d=indicators_dict["STOCH"]["d"],
                                             smooth_k=indicators_dict["STOCH"]["smooth"])
            #
            # stoch_df = TA.stoch(high=dataframe["high"], low=dataframe["low"], close=dataframe["close"],
            #                     k=indicators_dict["STOCH"]["k"], d=indicators_dict["STOCH"]["d"], smooth_k=indicators_dict["STOCH"]["smooth"], offset=0)
            stoch_k = round(stoch_df.iloc[:, 0], 2).fillna(0).values
            stoch_d = round(stoch_df.iloc[:, 1], 2).fillna(0).values
            dataframe["stoch_k"] = stoch_k
            dataframe["stoch_d"] = stoch_d

        if "RSI" in indicators_dict:
            rsi_df = TA.rsi(close=dataframe.close, length=indicators_dict["RSI"]["length"])
            dataframe["rsi"] = round(rsi_df.iloc[:], 2).fillna(0).values

        if "RSI2" in indicators_dict:
            rsi_df = TA.rsi(close=dataframe.close, length=indicators_dict["RSI2"]["length"])
            dataframe["rsi2"] = round(rsi_df.iloc[:], 2).fillna(0).values

        if "RSI14" in indicators_dict:
            rsi_df = TA.rsi(close=dataframe.close, length=indicators_dict["RSI14"]["length"])
            dataframe["rsi14"] = round(rsi_df.iloc[:], 2).fillna(0).values

        if "RSI10" in indicators_dict:
            rsi_df = TA.rsi(close=dataframe.close, length=indicators_dict["RSI10"]["length"])
            dataframe["rsi10"] = round(rsi_df.iloc[:], 2).fillna(0).values

        if "TVRSI" in indicators_dict:
            tv_rsi_df = tv_rsi(dataframe=dataframe, rsi_length=indicators_dict["TVRSI"]["rsi_length"], source=indicators_dict["TVRSI"]["source"],
                               ma_length=indicators_dict["TVRSI"]["ma_length"], ma_type=indicators_dict["TVRSI"]["ma_type"],
                               bb_mult=indicators_dict["TVRSI"]["bb_mult"])
            dataframe["tv_rsi"] = round(tv_rsi_df['rsi'], 2).fillna(0).values
            dataframe["tv_rsi_ma"] = round(tv_rsi_df['rsi_ma'], 2).fillna(0).values

        if "STOCHRSI" in indicators_dict:
            out = TA.stochrsi(dataframe[indicators_dict["STOCHRSI"]["rsi_source"]], length=indicators_dict["STOCHRSI"]["stochastic_length"], k=indicators_dict["STOCHRSI"]["k"], d=indicators_dict["STOCHRSI"]["d"],
                              rsi_length=indicators_dict["STOCHRSI"]["rsi_length"])
            dataframe["stochrsi_k"] = round(out.iloc[:, 0], 2).fillna(0).values
            dataframe["stochrsi_d"] = round(out.iloc[:, 1], 2).fillna(0).values

        if "MACD" in indicators_dict:
            macd_df = TA.macd(close=dataframe[indicators_dict["MACD"]["source"]], fast=indicators_dict["MACD"]["fast_length"],
                              slow=indicators_dict["MACD"]["slow_length"], signal=indicators_dict["MACD"]["signal_smoothing"], talib=True)
            dataframe["macd"] = round(macd_df.iloc[:, 0], 2).fillna(0).values
            dataframe["macd_h"] = round(macd_df.iloc[:, 1], 2).fillna(0).values
            dataframe["macd_s"] = round(macd_df.iloc[:, 2], 2).fillna(0).values

        if "BBAND" in indicators_dict:
            bband_df = TA.bbands(close=dataframe[indicators_dict["BBAND"]["source"]], length=indicators_dict["BBAND"]["length"], std=indicators_dict["BBAND"]["std_dev"],
                                 mamode=indicators_dict["BBAND"]["basis_ma_type"], offset=indicators_dict["BBAND"]["offset"])
            dataframe["bband_l"] = round(bband_df.iloc[:, 0], 2).fillna(0).values
            dataframe["bband_m"] = round(bband_df.iloc[:, 1], 2).fillna(0).values
            dataframe["bband_u"] = round(bband_df.iloc[:, 2], 2).fillna(0).values
            dataframe["bband_b"] = round(bband_df.iloc[:, 3], 2).fillna(0).values
            dataframe["bband_p"] = round(bband_df.iloc[:, 4], 2).fillna(0).values

        if "BBAND20" in indicators_dict:
            bband_df = TA.bbands(close=dataframe[indicators_dict["BBAND20"]["source"]], length=indicators_dict["BBAND20"]["length"], std=indicators_dict["BBAND20"]["std_dev"],
                                 mamode=indicators_dict["BBAND20"]["basis_ma_type"], offset=indicators_dict["BBAND20"]["offset"])
            dataframe["bband20_l"] = round(bband_df.iloc[:, 0], 2).fillna(0).values
            dataframe["bband20_m"] = round(bband_df.iloc[:, 1], 2).fillna(0).values
            dataframe["bband20_u"] = round(bband_df.iloc[:, 2], 2).fillna(0).values
            dataframe["bband20_b"] = round(bband_df.iloc[:, 3], 2).fillna(0).values
            dataframe["bband20_p"] = round(bband_df.iloc[:, 4], 2).fillna(0).values

        if "BBAND10" in indicators_dict:
            bband_df = TA.bbands(close=dataframe[indicators_dict["BBAND10"]["source"]], length=indicators_dict["BBAND10"]["length"], std=indicators_dict["BBAND10"]["std_dev"],
                                 mamode=indicators_dict["BBAND10"]["basis_ma_type"], offset=indicators_dict["BBAND10"]["offset"])
            dataframe["bband10_l"] = round(bband_df.iloc[:, 0], 2).fillna(0).values
            dataframe["bband10_m"] = round(bband_df.iloc[:, 1], 2).fillna(0).values
            dataframe["bband10_u"] = round(bband_df.iloc[:, 2], 2).fillna(0).values
            dataframe["bband10_b"] = round(bband_df.iloc[:, 3], 2).fillna(0).values
            dataframe["bband10_p"] = round(bband_df.iloc[:, 4], 2).fillna(0).values

        if "BBAND5" in indicators_dict:
            bband_df = TA.bbands(close=dataframe[indicators_dict["BBAND5"]["source"]], length=indicators_dict["BBAND5"]["length"], std=indicators_dict["BBAND5"]["std_dev"],
                                 mamode=indicators_dict["BBAND5"]["basis_ma_type"], offset=indicators_dict["BBAND5"]["offset"])
            dataframe["bband5_l"] = round(bband_df.iloc[:, 0], 2).fillna(0).values
            dataframe["bband5_m"] = round(bband_df.iloc[:, 1], 2).fillna(0).values
            dataframe["bband5_u"] = round(bband_df.iloc[:, 2], 2).fillna(0).values
            dataframe["bband5_b"] = round(bband_df.iloc[:, 3], 2).fillna(0).values
            dataframe["bband5_p"] = round(bband_df.iloc[:, 4], 2).fillna(0).values

        if "BBAND22" in indicators_dict:
            bband_df = TA.bbands(close=dataframe[indicators_dict["BBAND22"]["source"]], length=indicators_dict["BBAND22"]["length"], std=indicators_dict["BBAND22"]["std_dev"],
                                 mamode=indicators_dict["BBAND22"]["basis_ma_type"], offset=indicators_dict["BBAND22"]["offset"])
            dataframe["bband22_l"] = round(bband_df.iloc[:, 0], 2).fillna(0).values
            dataframe["bband22_m"] = round(bband_df.iloc[:, 1], 2).fillna(0).values
            dataframe["bband22_u"] = round(bband_df.iloc[:, 2], 2).fillna(0).values
            dataframe["bband22_b"] = round(bband_df.iloc[:, 3], 2).fillna(0).values
            dataframe["bband22_p"] = round(bband_df.iloc[:, 4], 2).fillna(0).values

        if "FISHER" in indicators_dict:
            fisher_df = TA.fisher(high=dataframe["high"], low=dataframe["low"], length=indicators_dict["FISHER"]["length"], signal=indicators_dict["FISHER"]["signal"])
            dataframe["fisher_t"] = round(fisher_df.iloc[:, 0], 2).fillna(0).values
            dataframe["fisher_s"] = round(fisher_df.iloc[:, 1], 2).fillna(0).values

        if "MOM" in indicators_dict:
            mom_df = TA.mom(close=dataframe[indicators_dict["MOM"]["source"]], length=indicators_dict["MOM"]["length"])
            dataframe["mom"] = round(mom_df.iloc[:], 2).fillna(0).values

        if "ROC" in indicators_dict:
            roc_df = TA.roc(close=dataframe[indicators_dict["ROC"]["source"]], length=indicators_dict["ROC"]["length"])
            dataframe["roc"] = round(roc_df.iloc[:], 2).fillna(0).values

        if "DPO" in indicators_dict:
            dpo_df = TA.dpo(close=dataframe["close"], length=indicators_dict["DPO"]["length"])
            dataframe["dpo"] = round(dpo_df.iloc[:], 2).fillna(0).values

        if "RVGI" in indicators_dict:
            rvgi_df = TA.rvgi(open_=dataframe["open"], high=dataframe["high"], low=dataframe["low"], close=dataframe["close"], length=indicators_dict["RVGI"]["length"],)
            dataframe["rvgi"] = round(rvgi_df.iloc[:, 0], 2).fillna(0).values
            dataframe["rvgi_s"] = round(rvgi_df.iloc[:, 1], 2).fillna(0).values

        if "WILLR" in indicators_dict:
            willr_df = TA.willr(high=dataframe["high"], low=dataframe["low"], close=dataframe["close"], length=indicators_dict["WILLR"]["length"])
            dataframe["willr"] = round(willr_df.iloc[:], 2).fillna(0).values

        if "VFI" in indicators_dict:
            vfi_df = volume_flow_indicator(dataframe=dataframe, length=indicators_dict["VFI"]["length"], coef=indicators_dict["VFI"]["coef"],
                                             vcoef=indicators_dict["VFI"]["vcoef"], signal_length=indicators_dict["VFI"]["signal_length"],
                                             smooth_vfi=indicators_dict["VFI"]["smooth_vfi"])
            dataframe["vfi"] = round(vfi_df['vfi'], 2).fillna(0).values
            dataframe["vfi_ma"] = round(vfi_df['vfi_ma'], 2).fillna(0).values
            dataframe["vfi_d"] = round(vfi_df['vfi_d'], 2).fillna(0).values

        if "VORTEX" in indicators_dict:
            vortex_df = TA.vortex(high=dataframe["high"], low=dataframe["low"], close=dataframe["close"], length=indicators_dict["VORTEX"]["length"])
            dataframe["vtx_p"] = round(vortex_df.iloc[:, 0], 2).fillna(0).values
            dataframe["vtx_m"] = round(vortex_df.iloc[:, 1], 2).fillna(0).values

        if "SUPERTREND" in indicators_dict:
            supertrend_df = TA.supertrend(high=dataframe["high"], low=dataframe["low"], close=dataframe["close"], length=indicators_dict["SUPERTREND"]["length"], multiplier=indicators_dict["SUPERTREND"]["multiplier"])
            dataframe["supertrend"] = round(supertrend_df.iloc[:, 0], 2).fillna(0).values
            dataframe["supertrend_d"] = round(supertrend_df.iloc[:, 1], 2).fillna(0).values

        if "FRACTAL" in indicators_dict:
            dataframe = williams_fractal(dataframe, fractal_window=indicators_dict["FRACTAL"]["length"])
            dataframe["fractal_up"] = dataframe["fractal_up"].fillna(0).values
            dataframe["fractal_down"] = dataframe["fractal_down"].fillna(0).values

        # if "TSI" in indicators_dict:
        #     tsi_df = TA.tsi(close=dataframe[indicators_dict["TSI"]["source"]], fast=indicators_dict["TSI"]["fast"], slow=indicators_dict["TSI"]["slow"], signal=indicators_dict["TSI"]["signal"])
        #     dataframe["tsi"] = round(tsi_df.iloc[:, 0]/100, 4).fillna(0).values
        #     dataframe["tsi_s"] = round(tsi_df.iloc[:, 1]/100, 4).fillna(0).values

        if "SMI" in indicators_dict:
            smi_df = TA.smi(close=dataframe[indicators_dict["SMI"]["source"]], fast=indicators_dict["SMI"]["fast"], slow=indicators_dict["SMI"]["slow"], signal=indicators_dict["SMI"]["signal"])
            dataframe["smi"] = round(smi_df.iloc[:, 0], 2).fillna(0).values
            dataframe["smi_s"] = round(smi_df.iloc[:, 1], 2).fillna(0).values
            dataframe["smi_o"] = round(smi_df.iloc[:, 2], 2).fillna(0).values

        if "TPR" in indicators_dict:
            dataframe["tpr"] = round((dataframe["high"] + dataframe["low"] + dataframe["close"])/3, 2)

        if "MAC" in indicators_dict:
            mac_u = TA.sma(close=dataframe["high"], length=indicators_dict["MAC"]["upper_length"])
            mac_l = TA.sma(close=dataframe["low"], length=indicators_dict["MAC"]["lower_length"])
            dataframe["mac_u"] = round(mac_u, 2).fillna(0).values
            dataframe["mac_l"] = round(mac_l, 2).fillna(0).values

        if "SQZMOM" in indicators_dict:
            sqzmom_df = squeeze_momentum(dataframe=dataframe, bb_length=indicators_dict["SQZMOM"]["bb_length"], bb_mult=indicators_dict["SQZMOM"]["bb_mult"],
                                         kc_length=indicators_dict["SQZMOM"]["kc_length"], kc_mult=indicators_dict["SQZMOM"]["kc_mult"],use_true_range=indicators_dict["SQZMOM"]["use_true_range"])
            dataframe["sqzmom"] = round(sqzmom_df, 2).fillna(0).values

        if "CHAIKIN" in indicators_dict:
            cv_df = chaikin_volatility(dataframe=dataframe, length=indicators_dict["CHAIKIN"]["length"], roc_length=indicators_dict["CHAIKIN"]["roc_length"])
            dataframe["chaikin"] = round(cv_df.iloc[:], 2).fillna(0).values

        if "VWAP" in indicators_dict:
            # vwap_df = TA.vwap(high=dataframe["high"], low=dataframe["low"], close=dataframe["close"], volume=dataframe["volume"])
            vwap_df = calculate_vwap(dataframe=dataframe)
            dataframe["vwap"] = round(vwap_df.iloc[:], 2).fillna(0).values

        if "DMI" in indicators_dict:
            dmi_df = calculate_dmi(dataframe=dataframe, adx_smoothing=indicators_dict["DMI"]["adx_smoothing"], di_length=indicators_dict["DMI"]["di_length"])
            dataframe["di_plus"] = round(dmi_df['di_plus'], 2).fillna(0).values
            dataframe["di_minus"] = round(dmi_df['di_minus'], 2).fillna(0).values
            dataframe["di_adx"] = round(dmi_df['di_adx'], 2).fillna(0).values

        if "YONO" in indicators_dict:
            yono_df = yono(dataframe=dataframe, depth=indicators_dict["YONO"]["depth"], deviation=indicators_dict["YONO"]["deviation"], backstep=indicators_dict["YONO"]["backstep"])
            dataframe["yono"] = yono_df.iloc[:, 0].values

        if "DEMA" in indicators_dict:
            dema_df = TA.dema(close=dataframe[indicators_dict["DEMA"]["source"]], length=indicators_dict["DEMA"]["length"])
            dataframe["dema"] = round(dema_df.iloc[:], 2).fillna(0).values

        if "TEMA" in indicators_dict:
            tema_df = TA.tema(close=dataframe[indicators_dict["TEMA"]["source"]], length=indicators_dict["TEMA"]["length"])
            dataframe["tema"] = round(tema_df.iloc[:], 2).fillna(0).values

        if "RVI" in indicators_dict:
            rvi_df = TA.rvi(close=dataframe["close"], high=dataframe["high"], low=dataframe["low"], length=indicators_dict["RVI"]["length"])
            dataframe["rvi"] = round(rvi_df.iloc[:], 2).fillna(0).values

        if "SHA" in indicators_dict:
            sha_df = heikin_ashi_smoothed(dataframe=dataframe, ema_length=indicators_dict["SHA"]["length"])
            dataframe["sha_1"] = sha_df.iloc[:, 0].fillna(0).values
            dataframe["sha_2"] = sha_df.iloc[:, 1].fillna(0).values

        if "JMA" in indicators_dict:
            jma_df = jurik_moving_average(dataframe=dataframe, length=indicators_dict["JMA"]["length"], phase=indicators_dict["JMA"]["phase"],
                                          power=indicators_dict["JMA"]["power"], source=indicators_dict["JMA"]["source"])
            dataframe["jma"] = round(jma_df.iloc[:, 0], 2).fillna(0).values
            dataframe["jma_c"] = jma_df.iloc[:, 1].fillna(0).values

        if "EFI" in indicators_dict:
            efi_df = TA.efi(close=dataframe["close"], volume=dataframe["volume"], length=indicators_dict["EFI"]["length"])
            dataframe["efi"] = round(efi_df, 2).fillna(0).values

        if "PSAR" in indicators_dict:
            psar_df = TA.psar(high=dataframe["high"], low=dataframe["low"], close=dataframe["close"], af0=indicators_dict["PSAR"]["start"],
                              af=indicators_dict["PSAR"]["increment"], max_af=indicators_dict["PSAR"]["max_value"])
            dataframe["psar_l"] = round(psar_df.iloc[:, 0], 2).fillna(0).values
            dataframe["psar_s"] = round(psar_df.iloc[:, 1], 2).fillna(0).values
            dataframe["psar_af"] = round(psar_df.iloc[:, 2], 2).fillna(0).values
            dataframe["psar_r"] = round(psar_df.iloc[:, 3], 2).fillna(0).values

        if "AVGVOL" in indicators_dict:
            avg_vol = average_volume(dataframe["volume"], length=indicators_dict["AVGVOL"]["length"])
            dataframe["avg_vol"] = round(avg_vol, 2).fillna(0).values

        if "BBPS" in indicators_dict:

            bbps_df = bb_sideways(dataframe=dataframe, bb_length=indicators_dict["BBPS"]["bb_length"], bb_mult=indicators_dict["BBPS"]["bb_mult"],
                                  bbr_len=indicators_dict["BBPS"]["bbr_len"], bbr_std_thresh=indicators_dict["BBPS"]["bbr_std_thresh"])
            dataframe["bbps_sideways"] = bbps_df.iloc[:, 0].fillna(False).values
            dataframe["bbps_color"] = bbps_df.iloc[:, 1].fillna(False).values

        if "RDX" in indicators_dict:
            rdx_df = calculate_rdx(dataframe=dataframe)
            dataframe["rdx"] = rdx_df.iloc[:, 0].values

        if "MTI" in indicators_dict:
            mti_df = calculate_mti(dataframe=dataframe, bb_length=indicators_dict["MTI"]["bb_length"], bb_mult=indicators_dict["MTI"]["bb_mult"],
                                   adx_length=indicators_dict["MTI"]["adx_length"], rsi_length=indicators_dict["MTI"]["rsi_length"])

        if "SADX" in indicators_dict:
            s_adx = smoothed_adx(dataframe=dataframe, adx_length=indicators_dict["SADX"]["adx_length"], di_length=indicators_dict["SADX"]["di_length"],
                                 smoothing_length=indicators_dict["SADX"]["smoothing_length"], mamode=indicators_dict["SADX"]["mamode"])
            dataframe["adx"] = round(s_adx.iloc[:, 0], 2).fillna(0).values
            dataframe["s_adx"] = round(s_adx.iloc[:, 1], 2).fillna(0).values

        if "NETVOLUME" in indicators_dict:
            net_volume = calculate_net_volume(dataframe=dataframe)
            dataframe["net_volume"] = round(net_volume, 2).fillna(0).values

        if "PPO" in indicators_dict:
            ppo_df = TA.ppo(close=dataframe["close"], fast=indicators_dict["PPO"]["fast_length"],
                            slow=indicators_dict["PPO"]["slow_length"])
            dataframe["ppo"] = round(ppo_df.iloc[:, 0], 2).fillna(0).values
            dataframe["ppo_h"] = round(ppo_df.iloc[:, 1], 2).fillna(0).values
            dataframe["ppo_s"] = round(ppo_df.iloc[:, 2], 2).fillna(0).values

        if "VOSC" in indicators_dict:
            v_osc = volume_oscillator(dataframe=dataframe, short_length=indicators_dict["VOSC"]["short_length"],
                                      long_length=indicators_dict["VOSC"]["long_length"])
            dataframe["v_osc"] = round(v_osc, 2).fillna(0).values

        if "VOLUMESLOPE" in indicators_dict:
            vol_slope_df = volume_slope(volume=dataframe["volume"], length=indicators_dict["VOLUMESLOPE"]["length"])
            dataframe["vol_ma"] = round(vol_slope_df.iloc[:, 0], 2).fillna(0).values
            dataframe["vol_slope"] = vol_slope_df.iloc[:, 1]

        if "OISLOPE" in indicators_dict:
            oi_slope_df = oi_slope(oi=dataframe["oi"], length=indicators_dict["OISLOPE"]["length"])
            dataframe["oi_ma"] = round(oi_slope_df.iloc[:, 0], 2).fillna(0).values
            dataframe["oi_slope"] = oi_slope_df.iloc[:, 1]

        if "BBW" in indicators_dict:
            bbw_df = bollinger_bandwidth(dataframe=dataframe, length=indicators_dict["BBW"]["length"], std_dev=indicators_dict["BBW"]["std_dev"],
                                         source=indicators_dict["BBW"]["source"], he_length=indicators_dict["BBW"]["he_length"],
                                         lc_length=indicators_dict["BBW"]["lc_length"])
            dataframe["bbw"] = round(bbw_df, 2).fillna(0).values
            # dataframe["bbw"] = bbw_df.fillna(0).values

        if "SBBW" in indicators_dict:
            sbbw_df = smoothed_bbw(dataframe=dataframe, length=indicators_dict["SBBW"]["length"],
                                   std_dev=indicators_dict["SBBW"]["std_dev"], source=indicators_dict["SBBW"]["source"],
                                   ma_type=indicators_dict["SBBW"]["ma_type"],
                                   ma_length=indicators_dict["SBBW"]["ma_length"])
            # dataframe["bbw"] = round(sbbw_df.iloc[:, 0].fillna(0), 2).values
            dataframe["sbbw"] = round(sbbw_df.iloc[:, 1].fillna(0), 2).values
            dataframe["sbbw_slope"] = sbbw_df.iloc[:, 2].fillna(0).values

        if "BBWRANGE" in indicators_dict:
            bbw_range = calculate_bbw_range(dataframe=dataframe, length=indicators_dict["BBWRANGE"]["length"], deviation=indicators_dict["BBWRANGE"]["deviation"])
            dataframe["bbw_range"] = bbw_range

        # if "TSI" in indicators_dict:
        #     tsi_df = calculate_tsi(close=dataframe["close"], period=indicators_dict["TSI"]["period"])
        #     dataframe["tsi"] = round(tsi_df, 2).fillna(0).values

        if "COPPOCK" in indicators_dict:
            coppock_df = TA.coppock(close=dataframe["close"], length=indicators_dict["COPPOCK"]["length"], fast=indicators_dict["COPPOCK"]["fast"],
                                    slow=indicators_dict["COPPOCK"]["slow"])
            dataframe["coppock"] = round(coppock_df, 2).fillna(0).values

        if "ORB" in indicators_dict:
            orb_up, orb_down = calculate_orb(dataframe=dataframe, start_time=indicators_dict["ORB"]["start_time"], end_time=indicators_dict["ORB"]["end_time"])
            dataframe["orb_up"] = orb_up
            dataframe["orb_down"] = orb_down

        if "CHOPZONE" in indicators_dict:
            cz_df = calculate_chop_zone(dataframe=dataframe, periods=indicators_dict["CHOPZONE"]["periods"])
            dataframe["chop_zone_color"] = cz_df.iloc[:, 0]

        if "SLOPE" in indicators_dict:
            slope_df = calculate_slope(dataframe=dataframe, source=indicators_dict["SLOPE"]["source"])
            dataframe[f'{indicators_dict["SLOPE"]["source"]}_slope'] = slope_df.iloc[:, 0]

        if "MCGD" in indicators_dict:
            mcgd_df = mcgd(close=dataframe["close"], length=indicators_dict["MCGD"]["length"])
            dataframe["mcgd"] = round(mcgd_df, 2).fillna(0).values

            # mcgd_df = TA.mcgd(close=dataframe["close"], length=indicators_dict["MCGD"]["length"])
            # dataframe["mcgd"] = round(mcgd_df.iloc[:], 2).fillna(0).values

        if "AO" in indicators_dict:
            ao_df = TA.ao(high=dataframe["high"], low=dataframe["low"])
            ao_diff = ao_df - ao_df.shift(1)
            dataframe["ao"] = round(ao_df, 2).fillna(0).values
            dataframe["ao_color"] = np.where(ao_diff > 0, "green", "red")

        if "WMA" in indicators_dict:
            wma_df = TA.wma(close=dataframe["close"], length=indicators_dict["WMA"]["length"])
            dataframe["wma"] = round(wma_df, 2).fillna(0).values

        if "WMA9" in indicators_dict:
            wma_df = TA.wma(close=dataframe["close"], length=indicators_dict["WMA9"]["length"])
            dataframe["wma9"] = round(wma_df, 2).fillna(0).values

        if "WMA30" in indicators_dict:
            wma_df = TA.wma(close=dataframe["close"], length=indicators_dict["WMA30"]["length"])
            dataframe["wma30"] = round(wma_df, 2).fillna(0).values

        if "VOLMA" in indicators_dict:
            if indicators_dict["VOLMA"]["mamode"] == "ema":
                volma_df = TA.ema(close=dataframe["volume"], length=indicators_dict["VOLMA"]["length"])
            else:
                volma_df = TA.sma(close=dataframe["volume"], length=indicators_dict["VOLMA"]["length"])
            dataframe["volma"] = round(volma_df, 2).fillna(0).values

        if "TAM" in indicators_dict:
            dataframe["tam_variant"] = tam_variant(dataframe=dataframe, ma_type=indicators_dict["TAM"]["ma_type"], src=indicators_dict["TAM"]["src"],
                                                   length=indicators_dict["TAM"]["length"], off_sig=indicators_dict["TAM"]["off_sig"], off_alma=indicators_dict["TAM"]["off_alma"])
        if "VOL_INDEX" in indicators_dict:
            vi_df = volatility_index(df=dataframe, length=indicators_dict["VOL_INDEX"]["length"], multiplier=indicators_dict["VOL_INDEX"]["multiplier"])
            dataframe["vol_index"] = round(vi_df["vol_index"], 2).fillna(0).values
            dataframe["vi_trend"] = vi_df["trend"]
            # dataframe["vi_long"] = vi_df["long_signal"]
            # dataframe["vi_short"] = vi_df["short_signal"]
            # dataframe["vi_signal"] = vi_df["signal"]
            prev_trend = dataframe["vi_trend"].shift(1)
            dataframe["vi_long"] = ((dataframe["vi_trend"] == True) & (prev_trend == False))
            dataframe["vi_short"] = ((dataframe["vi_trend"] == False) & (prev_trend == True))
            dataframe["vi_signal"] = ""
            dataframe.loc[dataframe["vi_long"], "vi_signal"] = "LONG"
            dataframe.loc[dataframe["vi_short"], "vi_signal"] = "SHORT"
        return dataframe

    except Exception as e:
        print(f"Exception in adding indicators : {e}")
        pass


def create_mt_report(trade_report, initial_deposit, file_name, logs_coll):
    """Function to Create Report in MetaTrader Report Format"""
    try:
        if not trade_report:
            return {}

        report_df = pd.DataFrame(trade_report)

        mt_dict = dict()
        mt_dict['initial_deposit'] = initial_deposit

        profit_trades = list(report_df[report_df['pnl'] > 0]['pnl'])
        loss_trades = list(report_df[report_df['pnl'] < 0]['pnl'])

        # Calculating Gross Profit
        gross_profit = round(sum(profit_trades), 2) if profit_trades else 0
        mt_dict['gross_profit'] = gross_profit

        # Calculating Gross Loss
        gross_loss = round(sum(loss_trades), 2) if loss_trades else 0
        mt_dict['gross_loss'] = gross_loss

        # Calculating Profit Factor
        mt_dict['profit_factor'] = round(abs(gross_profit / gross_loss), 2) if gross_loss else 0

        profitside = (len(profit_trades) / len(report_df)) * (gross_profit / len(profit_trades)) if profit_trades else 0
        lossside = (len(loss_trades) / len(report_df)) * (gross_loss / len(loss_trades)) if loss_trades else 0

        expected_payoff = round(profitside - lossside, 2)
        mt_dict['expected_payoff'] = expected_payoff

        equity_history = [initial_deposit]

        # report_pnl = [initial_deposit]
        # dates = [list(report_df['date'])[0]] + sorted(set(report_df['date']))

        report_df['date'] = pd.to_datetime(report_df['date'], format="%Y-%m-%d %H:%M:%S")

        eq_dates = [list(report_df['date'])[0].strftime('%Y-%m-%d')] + [i.strftime('%Y-%m-%d') for i in sorted(set(report_df['date']))]

        report_dt_group = report_df.groupby('date')

        for grp in report_dt_group.groups:
            equity_history.append(equity_history[-1]+sum(list(report_dt_group.get_group(grp)['pnl'])))

        # for pl in report_df['pnl']:
        #     equity_history.append(equity_history[-1] + pl)

        mt_dict['equity_history'] = list(zip(eq_dates, equity_history))
        # mt_dict['equity_history'] = list(zip(dates, report_pnl))

        # Calculating Absolute Drawdown
        min_drawdown = round(equity_history[0] - min(equity_history), 2)
        mt_dict['abs_drawdown'] = min_drawdown

        diff_points = list()

        if len(equity_history) >= 2:
            for prev_idx, curr_balance in enumerate(equity_history[1:], start=0):
                prev_balance = equity_history[prev_idx]
                # If the next balance is less, then only check that
                if prev_balance >= curr_balance:
                    difference = prev_balance - curr_balance
                    diff_points.append([prev_balance, curr_balance, difference])

        if diff_points:
            difference_li = [val[-1] for val in diff_points]
            relative_points = [val[2] / val[0] for val in diff_points]

            max_drawdown = max(difference_li)
            max_drawdown_per = round((max_drawdown / diff_points[difference_li.index(max_drawdown)][0]) * 100, 2)

            relative_drawdown = round(diff_points[relative_points.index(max(relative_points))][2], 2)
            relative_drawdown_per = round(max(relative_points) * 100, 2)
        else:
            max_drawdown = 0
            max_drawdown_per = 0
            relative_drawdown = 0
            relative_drawdown_per = 0

        mt_dict['maximal_drawdown'] = max_drawdown
        mt_dict['maximal_drawdown%'] = max_drawdown_per

        mt_dict['relative_drawdown'] = relative_drawdown
        mt_dict['relative_drawdown_per'] = relative_drawdown_per

        mt_dict['total_trades'] = len(report_df)

        signal_cnts = report_df['position_type'].value_counts().to_dict()

        if "LONG" not in signal_cnts:
            signal_cnts['LONG'] = 0
            long_pos_win = 0
        else:
            long_pos_win = round((len(report_df[report_df['position_type'] == "LONG"][report_df['pnl'] > 0]) / len(report_df) * 100), 2)

        if "SHORT" not in signal_cnts:
            signal_cnts['SHORT'] = 0
            short_pos_win = 0
        else:
            short_pos_win = round((len(report_df[report_df['position_type'] == "SHORT"][report_df['pnl'] > 0]) / len(report_df) * 100), 2)

        # # Short Position (Won%)
        mt_dict['short_position'] = signal_cnts['SHORT']
        mt_dict['short_position_won%'] = short_pos_win

        # # Long Position (Won%)
        mt_dict['long_position'] = signal_cnts['LONG']
        mt_dict['long_position_won%'] = long_pos_win

        # # Profit trades %
        mt_dict['profit_trades_num'] = len(profit_trades)
        mt_dict['profit_trades_num%'] = round((len(profit_trades) / len(report_df)) * 100, 2)

        # # Loss trades %
        mt_dict['loss_trades_num'] = len(loss_trades)
        mt_dict['loss_trades_num%'] = round((len(loss_trades) / len(report_df)) * 100, 2)

        # # The Largest profit trade
        if profit_trades:
            mt_dict['largest_profit_trade'] = max(profit_trades)
        else:
            mt_dict['largest_profit_trade'] = ""

        # # The Largest loss trade
        mt_dict['largest_loss_trade'] = min(loss_trades)

        # # Average Profit trade
        mt_dict['avg_profit_trade'] = round(gross_profit / len(profit_trades), 2)

        # # Average Loss trade
        mt_dict['avg_loss_trade'] = round(gross_loss / len(loss_trades), 2)

        consecutive_out = [1 if pnl > 0 else -1 for pnl in report_df['pnl']]
        cons_counts = [(x[0], len(list(x[1]))) for x in itertools.groupby(consecutive_out)]

        # Get Sum of those consecutive series
        final_cons_vals = []
        profit_loss_values = report_df['pnl'].values.tolist()
        st_idx = 0
        for (cons_type, cons_cnt) in cons_counts:
            final_cons_vals.append([cons_type, cons_cnt, profit_loss_values[st_idx: st_idx + cons_cnt]])
            st_idx += cons_cnt

        # Filter out the consecutive values
        cons_counts = {1: [], -1: []}

        for _ in final_cons_vals:
            if _[0] > 0:
                cons_counts[1].append(_)
            else:
                cons_counts[-1].append(_)
        # {cons_counts[1].append(_) if _[0] > 0 else cons_counts[-1].append(_) for _ in final_cons_vals}

        # # Maximum consecutive wins
        if len(cons_counts[1]) > 0:
            mt_dict['max_cons_wins_cnt'] = max(cons_counts[1], key=lambda x: x[1])[1]

            # # Maximal consecutive profit
            mt_dict['max_cons_wins_value'] = sum(max(cons_counts[1], key=lambda x: x[1])[2])

            # # Average consecutive wins
            mt_dict['avg_cons_wins'] = sum([val[1] for val in cons_counts[1]]) / len(cons_counts[1])
        else:
            mt_dict['max_cons_wins_cnt'] = 0
            mt_dict['max_cons_wins_value'] = 0
            mt_dict['avg_cons_wins'] = 0

        if len(cons_counts[-1]) > 0:
            # # Maximum consecutive loss
            mt_dict['max_cons_loss_cnt'] = max(cons_counts[-1], key=lambda x: x[1])[1]

            # # Maximal consecutive loss
            mt_dict['max_cons_loss_value'] = sum(max(cons_counts[-1], key=lambda x: x[1])[2])

            # # Average consecutive loss
            mt_dict['avg_cons_loss'] = sum([val[1] for val in cons_counts[-1]]) / len(cons_counts[-1])
        else:
            # # Maximum consecutive loss
            mt_dict['max_cons_loss_cnt'] = 0
            mt_dict['max_cons_loss_value'] = 0
            mt_dict['avg_cons_loss'] = 0

        for k, v in mt_dict.items():
            if type(v) in [np.float64, float]:
                mt_dict[k] = round(v, 2)

        return mt_dict

    except Exception as e:
        log_message = f"Exception in creating mt_report.\n{e}"
        print(log_message)
        mg_insert_log(logs_coll, file_name, 'ERROR', log_message, log_traceback=''.join(tb.format_exception(None, e, e.__traceback__)))
        return {}


def find_last_trading_date(market="IN"):
    """Function to Fetch Last Trading Date"""
    last_trading_date = None
    try:
        start_date = datetime.datetime.today() - datetime.timedelta(days=7)
        start_date = start_date.date()
        end_date = datetime.datetime.today().date()
        if market == "US":
            eod_candles = fetch_eod_candles(symbol="SPY", start_date=start_date, end_date=end_date)
        elif market == "IN":
            eod_candles = fetch_eod_candles(symbol="NIFTY 50", start_date=start_date, end_date=end_date)
        else:
            return datetime.datetime.today() - datetime.timedelta(days=1)

        if eod_candles:
            eod_df = pd.DataFrame(eod_candles)
            eod_df['date'] = pd.to_datetime(eod_df["date"])
            eod_df = eod_df.sort_values(by="date", ascending=True)
            last_trading_date = eod_df.to_dict('records')[-1]["date"]
        else:
            last_trading_date = datetime.datetime.today() - datetime.timedelta(days=1)
        return last_trading_date
    except Exception as e:
        print(f"Exception in fetching last trading date : {e}")
        return datetime.datetime.today() - datetime.timedelta(days=1)


def mg_insert_log(collection, file_name, log_level, log_message, request_id=None, strategy_id=None, user_id=None, log_traceback=None, api_route=None):
    """ Function to Insert Logs in MongoDB Logs"""
    log_dict = {'api_route': api_route, 'request_id': request_id, 'strategy_id': strategy_id, 'user_id': user_id,
                'file_name': file_name, 'log_level': log_level.upper(), 'timestamp': datetime.datetime.now(),
                'message': log_message, 'traceback': log_traceback}

    if not request_id:
        del log_dict['request_id']
    if not strategy_id:
        del log_dict['strategy_id']
    if not user_id:
        del log_dict['user_id']
    if not log_traceback:
        del log_dict['traceback']
    if not api_route:
        del log_dict['api_route']

    collection.insert_one(log_dict)


def dates_list_from_start_end(start, end):
    delta = end - start
    days = [start + datetime.timedelta(days=i) for i in range(delta.days + 1)]
    return days


def trading_dates_from_given_dates(st_date, en_date, db_collection, exchange='NSE', file_name=None, logs_coll=None):
    try:
        if exchange == 'NSE':
            symbol = 'NIFTY 50'
        else:
            symbol = 'NIFTY 50'

        trading_dates = db_collection.find({'symbol': symbol, 'date': {'$gte': st_date, '$lte': en_date}}).distinct('date')
    except Exception as e:
        log_message = f"Could not find TradingDates using database.\nReturning date list from given start date and end date.\n{e}\n"
        mg_insert_log(logs_coll, file_name, 'ERROR', log_message,
                      log_traceback=''.join(tb.format_exception(None, e, e.__traceback__)))

        trading_dates = dates_list_from_start_end(st_date, en_date)

    return trading_dates


def gnl_on_dates_on_given_time(dates_list, gnl_time, symbols_list, db_collection, gnl_stocks_length, file_name, logs_coll):
    gnl_dict = dict()
    top_gnl_length = int(gnl_stocks_length // 2)
    for dt in dates_list:
        try:
            timestamp = datetime.datetime.combine(dt.date(), gnl_time)
            data_li = list(db_collection.find({'symbol': {'$in': symbols_list}, 'timestamp': timestamp}))

            change_dict_at_given_time = dict()
            for data in data_li:
                symbol = data['symbol']
                try:
                    this_close = data['close']
                    previous_day_close = data['previous_day_close']
                    percentage_change = ((this_close - previous_day_close) / previous_day_close) * 100
                    change_dict_at_given_time[symbol] = percentage_change
                except Exception as e:
                    log_message = f"{symbol}: {dt}\n{e}\n"
                    mg_insert_log(logs_coll, file_name, 'ERROR', log_message,
                                  log_traceback=''.join(tb.format_exception(None, e, e.__traceback__)))
                    continue

            change_sorted = sorted(change_dict_at_given_time.items(), key=lambda x: x[1], reverse=True)
            gainers = [x[0] for x in change_sorted[:top_gnl_length]]
            losers = [x[0] for x in change_sorted[top_gnl_length.__neg__():]]
            gnl_dict[dt] = {'gainers': gainers, 'losers': losers}

        except Exception as e:
            log_message = f"Exception in getting GnL Dict for date: {dt}\n{e}\n"
            mg_insert_log(logs_coll, file_name, 'ERROR', log_message,
                          log_traceback=''.join(tb.format_exception(None, e, e.__traceback__)))
            continue

    return gnl_dict


def get_fibonacci_pivot_points(high, low, close, level1=0.382, level2=0.618, level3=1.0, file_name=None, logs_coll=None):
    """ Function to get previous date ohlc and then apply fibonacci pivot points """
    '''
    Formula:
        - pivot = (h + l + c) / 3  # variants duplicate close or add open
        - support1 = p - level1 * (high - low)  # level1 0.382
        - support2 = p - level2 * (high - low)  # level2 0.618
        - support3 = p - level3 * (high - low)  # level3 1.000
        - resistance1 = p + level1 * (high - low)  # level1 0.382
        - resistance2 = p + level2 * (high - low)  # level2 0.618
        - resistance3 = p + level3 * (high - low)  # level3 1.000
    '''

    try:
        candle_length = abs(high - low)

        p = round((high + low + close) / 3, 2)

        r1 = round(p + level1 * candle_length, 2)
        r2 = round(p + level2 * candle_length, 2)
        r3 = round(p + level3 * candle_length, 2)

        s1 = round(p - level1 * candle_length, 2)
        s2 = round(p - level2 * candle_length, 2)
        s3 = round(p - level3 * candle_length, 2)
    except Exception as e:
        log_message = f"Exception in calculating Fibonacci Pivot points.\nReturning None\n{e}\n"
        mg_insert_log(logs_coll, file_name, 'ERROR', log_message,
                      log_traceback=''.join(tb.format_exception(None, e, e.__traceback__)))
        return None, None, None, None, None, None, None

    return p, r1, r2, r3, s1, s2, s3


def get_lot_size(stocks_li, exchange='NSE', segment='future', kite_api_key=None, file_name=None, logs_coll=None):
    lot_size_dict = dict()
    try:
        if exchange == 'NSE':
            from kiteconnect import KiteConnect
            kite_obj = KiteConnect(kite_api_key)
            stocks_df = pd.DataFrame(kite_obj.instruments(exchange='NFO'))
            if segment == 'future':
                fut_df = stocks_df[stocks_df['instrument_type'] == 'FUT']

                for symbol in stocks_li:
                    try:
                        if symbol == 'NIFTY 50':
                            symbol = 'NIFTY'
                        if symbol == 'NIFTY BANK':
                            symbol = 'BANKNIFTY'

                        stock_df = fut_df[fut_df['name'] == symbol]
                        lot_size = list(stock_df['lot_size'])[0]

                        if symbol == 'NIFTY':
                            symbol = 'NIFTY 50'
                        if symbol == 'BANKNIFTY':
                            symbol = 'NIFTY BANK'

                        lot_size_dict[symbol] = lot_size
                    except Exception as e:
                        lot_size_dict[symbol] = 1
                        log_message = f"Exception in getting lot size of {symbol}.\nSetting lot_size of this symbol to 1\n{e}\n"
                        mg_insert_log(logs_coll, file_name, 'ERROR', log_message,
                                      log_traceback=''.join(tb.format_exception(None, e, e.__traceback__)))

    except Exception as e:
        log_message = f"Exception in get_lot_size function\n{e}\n"
        mg_insert_log(logs_coll, file_name, 'ERROR', log_message,
                      log_traceback=''.join(tb.format_exception(None, e, e.__traceback__)))

    return lot_size_dict


def near_value(position_type, operation, current_value, near_pct, file_name, logs_coll):
    value = current_value
    try:
        near_pct /= 100
        if position_type == 'LONG':
            if operation == 'ENTRY':
                value = current_value * (1 + near_pct)
            elif operation == 'EXIT':
                value = current_value * (1 - near_pct)

        elif position_type == 'SHORT':
            if operation == 'ENTRY':
                value = current_value * (1 - near_pct)
            elif operation == 'EXIT':
                value = current_value * (1 + near_pct)
        else:
            value = current_value
            log_message = f"position_type does not match with 'LONG' or 'SHORT'"
            mg_insert_log(logs_coll, file_name, 'ERROR', log_message)
    except Exception as e:
        log_message = f"Exception in finding near value.\nReturning same value as given\n{e}\n"
        mg_insert_log(logs_coll, file_name, 'ERROR', log_message,
                      log_traceback=''.join(tb.format_exception(None, e, e.__traceback__)))
        value = current_value

    return value


def get_pnl(position_type, entry_p, exit_p, lot_size, file_name, logs_coll):
    try:
        if position_type == 'LONG':
            points_gain = (exit_p - entry_p)
            pnl = points_gain * lot_size

        elif position_type == 'SHORT':
            points_gain = (entry_p - exit_p)
            pnl = points_gain * lot_size

        else:
            points_gain = "Error in points gain calculation"
            pnl = 'Error in pnl calculation'

        return points_gain, pnl
    except Exception as e:
        log_message = f"Could not calculate pnl using get_pnl function."
        mg_insert_log(logs_coll, file_name, 'ERROR', log_message,
                      log_traceback=''.join(tb.format_exception(None, e, e.__traceback__)))
        return 0, 0


def calculate_margin(price, lot_sizes):
    """ Function to calculate future margin of Top GL """
    future_margin = 0
    margin = {}
    for stock in price:
        margin[stock] = price[stock] * lot_sizes[stock]
        future_margin += price[stock] * lot_sizes[stock]

    return future_margin,margin


def calculate_margin_percent(price, margin, lot_sizes):
    """ Function to calculate margin percentage """
    margin_percent = {}
    for stock in price:
        percent = (price[stock]*lot_sizes[stock])* (100/margin)
        margin_percent[stock] = percent
    return margin_percent


def calculate_amount_distribution(percent_distribution, investment_amount):
    """ Function to calculate Investment Amount using percentage distribution """
    amount_distribution = {}
    for stock in percent_distribution:
        amount_distribution[stock] = investment_amount * percent_distribution[stock]/100
    return amount_distribution


def calculate_share_distribution(price, amount_distribution, file_name, logs_coll):
    """ Function to calculate share distribution of Top GL Stocks """
    share_distribution = {}
    for stock in price:
        try:
            _shares = round(amount_distribution[stock] / price[stock])
            if _shares <= 0:
                _shares = 1
            share_distribution[stock] = _shares
        except Exception as e:
            log_message = f"Error in calculating share_distribution - {stock} {amount_distribution} {price}"
            mg_insert_log(logs_coll, file_name, 'ERROR', log_message, log_traceback=''.join(tb.format_exception(None, e, e.__traceback__)))
            share_distribution[stock] = 1
    return share_distribution


def calculate_distribution(price, lot_sizes, investment_amount):
    """ Function to calculate number of shares to buy/sell """

    future_margin, margin = calculate_margin(price, lot_sizes)
    margin_percent = calculate_margin_percent(price, future_margin, lot_sizes)
    amount_distribution = calculate_amount_distribution(margin_percent, investment_amount)
    # share_distribution = calculate_share_distribution(price, amount_distribution)

    return future_margin, margin_percent, amount_distribution #, share_distribution


def fetch_available_funds(credential_id):
    """Function to fetch current available funds in the account"""
    try:
        print(f"***** Fetching Available Funds for : {credential_id} *****")
        response = requests.post(urljoin(orders_url, "get_broker_fund"), json={"credential_id": credential_id})
        response_dict = response.json()
        if response_dict["status"] == "SUCCESS" and response_dict["message"] == "Fund Found":
            fund_available = response_dict["data"]["net_balance"]
            print(f"fund_available : {fund_available}")
            return fund_available
    except Exception as e:
        print(f"Exception in Fetching Available Funds : {e}")
        return None


def calculate_funds(investment, available_funds):
    """ Function to calculate Funds required while placing order """
    try:
        print("Calculating Funds Required")
        if investment < available_funds:
            return investment
        else:
            return available_funds

    except Exception as e:
        print("Exception in calculating funds : {}".format(e))
        pass


def round_to_tick_multiple(input_price):
    """Function to round price to nearest tick multiple"""
    try:
        rounded_price = round((math.ceil(input_price * 20) / 20), 2)
        # print("price : {} | rounded_price : {}".format(input_price, rounded_price))
        return rounded_price
    except Exception as e:
        print("Exception in round to tick multiple : {}".format(e))
        pass


def send_order_alert(alert_dict):
    """Function to Send Alert on Order"""
    try:
        print("Sending Alert")
        response = requests.post(url=urljoin(orders_url, "send_notification"), json=alert_dict)
        print("response : {}".format(response.json()))
    except Exception as e:
        print("Exception in sending alert : {}".format(e))
        pass


def calculate_brokerage(buy_price, sell_price, quantity, broker="zerodha", market_type="options", order_type="MARKET", lot_size=100, position_type="LONG", holding_type="intraday", no_of_orders=2, market="IN", exchange="NSE"):
    """Function to calculate brokerage"""
    try:

        if broker == "zerodha":

            if market == "IN":
                gst = 0.18
                sebi_fees = 0.0001
                clearing_charge = 0

                # Calculating Turn Over
                turnover = (buy_price * quantity) + (sell_price * quantity)

                if market_type == "equity" and holding_type == "delivery":
                    broker_fees = 15.34
                    transaction_fees = 0.00297 if exchange == "NSE" else 0.00375
                    stt_fees = 0.1
                    stamp_fees = 0.015

                    # Calculating STT Charges
                    buy_stt = round((quantity * buy_price * stt_fees) / 100, 2)
                    sell_stt = round((quantity * sell_price * stt_fees) / 100, 2)
                    stt_charge = buy_stt + sell_stt

                    # Calculating Transaction Fees
                    transaction_charge = round(turnover * transaction_fees/100, 2)

                    # Calculating Stamp Fees
                    stamp_charge = round((quantity * buy_price * stamp_fees)/100, 2)

                elif market_type == "equity" and holding_type == "intraday":
                    broker_fees_1 = 20 * no_of_orders
                    broker_fees_2 = round(turnover * (0.03 / 100), 2)
                    broker_fees = min(broker_fees_1, broker_fees_2)

                    transaction_fees = 0.00297 if exchange == "NSE" else 0.00375
                    stamp_fees = 0.003
                    stt_fees = 0.025

                    # Calculating STT Charge
                    stt_charge = round(quantity * sell_price * stt_fees / 100, 2)

                    # Calculating Transaction Fees
                    transaction_charge = round(turnover * transaction_fees / 100, 2)

                    # Calculating Stamp Fees
                    stamp_charge = round(quantity * buy_price * stamp_fees / 100, 2)

                elif market_type == "futures":
                    broker_fees_1 = 20 * no_of_orders
                    broker_fees_2 = round(turnover * (0.03 / 100), 2)
                    broker_fees = min(broker_fees_1, broker_fees_2)
                    transaction_fees = 0.00173 if exchange == "NSE" else 0
                    stamp_fees = 0.002
                    stt_fees = 0.02

                    # Calculating STT Charge
                    stt_charge = round(quantity * sell_price * stt_fees / 100)

                    # Calculating Transaction Fees
                    transaction_charge = round(turnover * transaction_fees / 100, 2)

                    # Calculating Stamp Fees
                    stamp_charge = round(quantity * buy_price * stamp_fees / 100, 2)

                else:
                    broker_fees = 20 * no_of_orders
                    transaction_fees = 0.03503 if exchange == "NSE" else 0.0325
                    stamp_fees = 0.003

                    stt_fees = 0.1

                    # Calculating STT Charge
                    stt_charge = round(quantity * sell_price * stt_fees / 100)

                    # Calculating Stamp Fees
                    stamp_charge = round(quantity * buy_price * stamp_fees / 100, 2)

                    # Calculating Transaction Fees
                    transaction_charge = round(turnover * transaction_fees / 100, 2)

                # Calculating Sebi Charges
                sebi_charge = round(turnover * sebi_fees/100, 2)

                total_charges = broker_fees + sebi_charge + transaction_charge

                # Total GST Charges
                gst = round(total_charges * gst, 2)

                # Calculating Total tax and Charges
                total_charges = round((broker_fees + sebi_charge + transaction_charge + stt_charge + clearing_charge + stamp_charge + gst), 2)

                # Calculating Net PnL
                if position_type.upper() == "LONG":
                    net_pl = round(((sell_price - buy_price) * quantity) - total_charges, 2)
                else:
                    net_pl = round(((buy_price - sell_price) * quantity) - total_charges, 2)

                return total_charges, net_pl

        elif broker == "coindcx":
            brokerage = 0.5
            buy_turnover = buy_price * quantity
            sell_turnover = sell_price * quantity
            buy_charges = round(buy_turnover * brokerage/100, 2)
            sell_charges = round(sell_turnover * brokerage/100, 2)
            total_charges = buy_charges + sell_charges
            if position_type.upper() == "LONG":
                net_pl = round(((sell_price - buy_price) * quantity) - total_charges, 2)
            else:
                net_pl = round(((buy_price - sell_price) * quantity) - total_charges, 2)
            return total_charges, net_pl

        elif broker == "binance":
            fee_rates = {
                "spot": {"maker": 0.001, "taker": 0.001},
                "futures": {"maker": 0.0002, "taker": 0.0004}
            }

            m_t = "maker" if order_type == "LIMIT" else "taker"
            fee_rate = fee_rates[market_type][m_t]

            # Calculate position size (margin * leverage)
            entry_price = buy_price if position_type.upper() == "LONG" else sell_price
            position_size = quantity * entry_price

            # Calculate gross PnL
            if position_type.upper() == "SHORT":
                gross_profit = (buy_price - sell_price) * quantity
            else:
                gross_profit = (sell_price - buy_price) * quantity

            fee_per_trade = position_size * fee_rate
            total_charges = fee_per_trade * 2

            net_pnl = gross_profit - total_charges
            return total_charges, net_pnl

        elif broker == "schwab":
            if market_type == "options":
                commission_per_contract = 0.65
                regulatory_per_contract = 0.04
                contracts = quantity / lot_size

                buy_fees = contracts * commission_per_contract
                sell_fees = contracts * (commission_per_contract + regulatory_per_contract)

                total_charges = buy_fees + sell_fees

                if position_type.upper() == "LONG":
                    net_pl = round(((sell_price - buy_price) * quantity) - total_charges, 2)
                else:
                    net_pl = round(((buy_price - sell_price) * quantity) - total_charges, 2)
                return total_charges, net_pl

            else:  # equities
                commission = 0.0
                sec_fee_rate = 0.000008
                finra_taf_rate = 0.000166
                finra_taf_cap = 8.30

                sell_value = sell_price * quantity
                sec_fee = sell_value * sec_fee_rate
                finra_fee = min(quantity * finra_taf_rate, finra_taf_cap)

                total_charges = commission + sec_fee + finra_fee

                if position_type.upper() == "LONG":
                    net_pl = round(((sell_price - buy_price) * quantity) - total_charges, 2)
                else:
                    net_pl = round(((buy_price - sell_price) * quantity) - total_charges, 2)
                return total_charges, net_pl

        elif broker == "interactive_brokers" or broker == "ibkr":
            if market_type == "options":
                # IBKR Options pricing: $0.65 per contract, $0.50 min per order
                commission_per_contract = 0.65
                min_commission_per_order = 0.50
                contracts = quantity / lot_size

                # Calculate commission for buy and sell
                buy_commission = max(contracts * commission_per_contract, min_commission_per_order)
                sell_commission = max(contracts * commission_per_contract, min_commission_per_order)

                # Regulatory fees (Options Regulatory Fee - ORF)
                orf_rate = 0.0455  # per contract
                orf_fee = contracts * orf_rate * 2  # buy and sell

                # FINRA Trading Activity Fee (TAF) - on sells only
                finra_taf_rate = 0.002  # per contract, max $5.95 per trade
                finra_taf = min(contracts * finra_taf_rate, 5.95)

                # SEC Transaction Fee - on sells only
                sell_value = sell_price * quantity
                sec_fee_rate = 0.0000278  # per dollar of sale
                sec_fee = round(sell_value * sec_fee_rate, 2)

                total_charges = buy_commission + sell_commission + orf_fee + finra_taf + sec_fee

                if position_type.upper() == "LONG":
                    net_pl = round(((sell_price - buy_price) * quantity) - total_charges, 2)
                else:
                    net_pl = round(((buy_price - sell_price) * quantity) - total_charges, 2)
                return total_charges, net_pl

            elif market_type == "futures":
                # IBKR Futures pricing: Tiered pricing
                # Simplified model - $0.85 per contract for US futures
                commission_per_contract = 0.85
                contracts = quantity / lot_size

                buy_commission = contracts * commission_per_contract
                sell_commission = contracts * commission_per_contract

                # Exchange and regulatory fees (varies by exchange, using typical CME rates)
                exchange_fee = contracts * 1.50 * 2  # buy and sell
                nfa_fee = contracts * 0.02 * 2  # NFA regulatory fee

                total_charges = buy_commission + sell_commission + exchange_fee + nfa_fee

                if position_type.upper() == "LONG":
                    net_pl = round(((sell_price - buy_price) * quantity) - total_charges, 2)
                else:
                    net_pl = round(((buy_price - sell_price) * quantity) - total_charges, 2)
                return total_charges, net_pl

            else:  # equities - IBKR Tiered pricing
                # Tiered pricing: $0.0035 per share, $0.35 min, 0.5% max of trade value
                commission_per_share = 0.0035
                min_commission = 0.35

                # Calculate commission for buy and sell
                buy_value = buy_price * quantity
                sell_value = sell_price * quantity

                buy_commission = max(min(quantity * commission_per_share, buy_value * 0.005), min_commission)
                sell_commission = max(min(quantity * commission_per_share, sell_value * 0.005), min_commission)

                # SEC Transaction Fee - on sells only
                sec_fee_rate = 0.0000278  # per dollar of sale
                sec_fee = round(sell_value * sec_fee_rate, 2)

                # FINRA Trading Activity Fee (TAF) - on sells only
                finra_taf_rate = 0.000166  # per share
                finra_taf_cap = 8.30
                finra_taf = min(quantity * finra_taf_rate, finra_taf_cap)

                total_charges = buy_commission + sell_commission + sec_fee + finra_taf

                if position_type.upper() == "LONG":
                    net_pl = round(((sell_price - buy_price) * quantity) - total_charges, 2)
                else:
                    net_pl = round(((buy_price - sell_price) * quantity) - total_charges, 2)
                return total_charges, net_pl

        elif broker == "dukascopy":
            if market == "FOREX":
                # Only charge: volume commission (round-trip = open + close)
                # Rate: USD per $1M traded (default $35 for base tier)
                commission_rate_per_million = 35

                buy_commission = (quantity * buy_price / 1000000) * commission_rate_per_million
                sell_commission = (quantity * sell_price / 1000000) * commission_rate_per_million

                total_charges = round(buy_commission + sell_commission, 6)

                if position_type.upper() == "LONG":
                    net_pl = round(((sell_price - buy_price) * quantity) - total_charges, 2)
                else:
                    net_pl = round(((buy_price - sell_price) * quantity) - total_charges, 2)

                return total_charges, net_pl
    except Exception as e:
        print(f"Exception in calculating brokerage : {e}")
        pass


def merge_candle(candle_1, candle_2):
    """ Function to merge input candles """
    try:
        output_candle = candle_1.copy()
        output_candle["high"] = max([candle_1["high"], candle_2["high"]])
        output_candle["low"] = min([candle_1["low"], candle_2["low"]])
        output_candle["timestamp"] = candle_2["timestamp"]
        if "volume" in candle_1:
            output_candle["volume"] = sum([candle_1["volume"], candle_2["volume"]])
        if "oi" in candle_1:
            output_candle["oi"] = sum([candle_1["oi"], candle_2["oi"]])
        return output_candle
    except Exception as e:
        print(f"Exception in merging candle : {e}")
        pass


def convert_candle_pattern(dataframe, pattern):
    """ Function to convert a candle pattern """
    try:
        print("converting candle dataframe to : {}".format(pattern))
        if pattern == 'heikin_ashi':
            ha_df = dataframe.copy()
            ha_df['open'] = 0.0
            # Setting Close Values
            ha_df['close'] = (dataframe['open'] + dataframe['high'] + dataframe['low'] + dataframe['close']) / 4

            for i in range(0, len(dataframe)):
                if i == 0:
                    ha_df.loc[0, 'open'] = (dataframe['open'][i] + dataframe['close'][i]) / 2
                else:
                    ha_df.loc[i, 'open'] = (ha_df.loc[i - 1, 'open'] + ha_df.loc[i - 1, 'close']) / 2

                # ha_df.loc[i, 'ha_color'] = 'green' if ha_df['close'][i] > ha_df['open'][i] else 'red'

            ha_df['high'] = ha_df[['high', 'open', 'close']].max(axis=1)
            ha_df['low'] = ha_df[['low', 'open', 'close']].min(axis=1)

            return ha_df

        if pattern == 'ask':
            last_candle = None
            output_list = []
            candles_list = dataframe.to_dict('records')

            for c_index, candle in enumerate(candles_list):
                if c_index == 0:
                    last_candle = candle
                else:
                    # Finding Highest between Open and Close Price
                    hp = max([last_candle["open"], last_candle["close"]])

                    # Finding Lowest between Open and Close Price
                    lp = min([last_candle["open"], last_candle["close"]])

                    # Checking Inside Body Candle condition
                    if lp <= candle['open'] <= hp and lp <= candle['close'] <= hp:
                        # Merging To Last Candle
                        last_candle = merge_candle(candle_1=last_candle, candle_2=candle)
                    else:
                        output_list.append(last_candle)

                        # Reassigning Last Candle
                        last_candle = candle

                    # market_exit_time = datetime.datetime.strptime("15:20", '%H:%M').time()

                    # if candle["timestamp"].time() < market_exit_time:
                    #     # Checking Inside Body Candle condition
                    #     if lp <= candle['open'] <= hp and lp <= candle['close'] <= hp:
                    #         # Merging To Last Candle
                    #         last_candle = merge_candle(candle_1=last_candle, candle_2=candle)
                    #     else:
                    #         output_list.append(last_candle)
                    #
                    #         # Reassigning Last Candle
                    #         last_candle = candle
                    # else:
                    #     output_list.append(candle)
            output_list.append(last_candle)
            ask_df = pd.DataFrame(output_list)
            return ask_df
    except Exception as e:
        print("exception in converting candle pattern : {}".format(e))
        pass


def convert_candle_to_hka(previous_candle, current_candle):
    """ Function to convert single candle to heikin-ashi """
    try:
        print("converting candle to heikin_ashi")
        hka_candle = current_candle.copy()
        hka_candle["open"] = round((previous_candle["open"] + previous_candle["close"]) / 2, 2)
        hka_candle["close"] = round((current_candle['open'] + current_candle['high'] + current_candle['low'] + current_candle['close']) / 4, 2)
        hka_candle['high'] = round(max([hka_candle['high'], hka_candle['open'], hka_candle['close']]), 2)
        hka_candle['low'] = round(min([hka_candle['low'], hka_candle['open'], hka_candle['close']]), 2)
        return hka_candle
    except Exception as e:
        print(f"Exception in converting single candle to hka : {e}")
        return current_candle


def nearest_expiry_option_data(option_candle_list):
    try:
        expiry_dates = sorted([datetime.datetime.strptime(candle['expiry'], "%Y-%m-%d") for candle in option_candle_list])
        expiry_find = datetime.datetime.strftime(expiry_dates[0], "%Y-%m-%d")
        option_candle_df = pd.DataFrame(option_candle_list)
        option_candle_df.drop_duplicates(inplace=True)
        option_candle_df = option_candle_df[option_candle_df['expiry'] == expiry_find]

        return option_candle_df.to_dict('records')
    except Exception as e:
        print("error in filtering option data for nearest expiry")
        return []


def find_nearest_strike_price(est_strike_price):
    """ Function to find nearest strike price from Option Chain"""
    try:
        return round(est_strike_price, -2)
    except Exception as e:
        print("Exception in finding nearest strike price : {}".format(e))
        pass


def generate_mt_report(report_df, pnl_column='net_pnl'):
    """ Function to generate an MT report"""
    try:
        print("Generating MT Report")
        out_dict = {}
        print(f"report_df : ")
        print(report_df.head())

        initial_deposit = report_df['investment'][0]

        # Total trades
        out_dict['total_trades'] = len(report_df)

        profit_trades = report_df[report_df[pnl_column] > 0][pnl_column]
        loss_trades = report_df[report_df[pnl_column] < 0][pnl_column]

        gross_profit = profit_trades.sum()
        gross_loss = loss_trades.sum()

        out_dict['gross_profit'] = gross_profit
        out_dict['gross_loss'] = gross_loss

        # Total Net Profit - Sum of all profit/loss
        out_dict['total_net_profit'] = report_df[pnl_column].sum()

        # Profit trades %
        out_dict['profit_trades_num'] = len(profit_trades)
        out_dict['profit_trades_num%'] = (len(profit_trades) / len(report_df)) * 100
        out_dict['largest_profit_trade'] = max(profit_trades) if profit_trades.any() else 0
        out_dict['avg_profit_trade'] = gross_profit / len(profit_trades) if gross_profit.any() else 0
        out_dict['avg_profit_per_trade'] = out_dict['total_net_profit'] / out_dict['total_trades']

        # Loss trades %
        out_dict['loss_trades_num'] = len(loss_trades)
        out_dict['loss_trades_num%'] = (len(loss_trades) / len(report_df)) * 100
        out_dict['largest_loss_trade'] = min(loss_trades) if loss_trades.any() else 0
        out_dict['avg_loss_trade'] = gross_loss / len(loss_trades) if loss_trades.any() else 0

        # Calculating Profit factor
        try:
            out_dict['profit_factor'] = abs(gross_profit / gross_loss)
        except Exception as e:
            out_dict['profit_factor'] = 0

        # Expected Payoff
        profit_side = (len(profit_trades) / len(report_df)) * (gross_profit / len(profit_trades))
        loss_side = (len(loss_trades) / len(report_df)) * (gross_loss / len(loss_trades))
        out_dict['expected_payoff'] = profit_side - loss_side

        # Calculating Equity history (Balance change history)
        equity_history = []
        for pl in report_df[pnl_column]:
            if not equity_history:
                equity_history.append(initial_deposit + pl)
            else:
                equity_history.append(equity_history[-1] + pl)

        # Calculating Absolute drawdown
        min_drawdown = min(equity_history) if equity_history else 0
        out_dict['abs_drawdown'] = round(equity_history[0] - min_drawdown, 2)
        out_dict['abs_drawdown%'] = round((out_dict['abs_drawdown'] / equity_history[0]) * 100, 2)

        # Calculating Dropdown Points
        diff_points = []
        for prev_idx, val in enumerate(equity_history[1:], 0):
            # If the next balance is less then only check that
            if equity_history[prev_idx] >= val:
                diff_points.append([equity_history[prev_idx], val])

        # Calculating Maximal drawdown
        if diff_points:
            _difference = [i[0] - i[1] for i in diff_points]
            max_drawdown = max(_difference)
            out_dict['maximal_drawdown'] = max_drawdown
            out_dict['maximal_drawdown%'] = round((max_drawdown / diff_points[_difference.index(max_drawdown)][0]) * 100, 2)
        else:
            out_dict['maximal_drawdown'] = 0
            out_dict['maximal_drawdown%'] = 0

        # Calculating Relative draw down
        max_value = equity_history[0]
        rel_drawdown = 0
        for value in equity_history:
            if value > max_value:
                max_value = value
            else:
                current_drawdown = max_value - value
                if current_drawdown > rel_drawdown:
                    rel_drawdown = current_drawdown

        out_dict['relative_drawdown'] = rel_drawdown
        out_dict['relative_drawdown%'] = (rel_drawdown / max_value) * 100

        signal_cnts = report_df['position_type'].value_counts().to_dict()

        if 'SHORT' not in signal_cnts:
            signal_cnts['SHORT'] = 0

        if 'LONG' not in signal_cnts:
            signal_cnts['LONG'] = 0

        _short_pos_win = 0 if "SHORT" not in signal_cnts else round((len(report_df[report_df['position_type'] == "SHORT"][report_df[pnl_column] > 0]) / len(report_df) * 100), 2)
        _long_pos_win = 0 if "LONG" not in signal_cnts else round((len(report_df[report_df['position_type'] == "LONG"][report_df[pnl_column] > 0]) / len(report_df) * 100), 2)

        # Short Position
        try:
            out_dict['short_position'] = signal_cnts['SHORT']
            out_dict['short_position(win%)'] = _short_pos_win
        except:
            out_dict['short_position'] = 0
            out_dict['short_position(win%)'] = 0

        # Long Position
        try:
            out_dict['long_position'] = signal_cnts['LONG']
            out_dict['long_position(win%)'] = _long_pos_win
        except:
            out_dict['long_position'] = 0
            out_dict['long_position(win%)'] = 0

        CONS_out = [1 if _ > 0 else -1 for _ in report_df[pnl_column]]
        cons_counts = [(x[0], len(list(x[1]))) for x in itertools.groupby(CONS_out)]

        # Get Sum of those CONS series
        final_cons_vals = []
        profit_loss_values = report_df[pnl_column].values.tolist()
        st_idx = 0
        for (cons_type, cons_cnt) in cons_counts:
            final_cons_vals.append([cons_type, cons_cnt, profit_loss_values[st_idx: st_idx + cons_cnt]])
            st_idx += cons_cnt

        # Filter out the CONS values
        cons_counts = {'1': [], '-1': []}
        for _ in final_cons_vals:
            if _[0] > 0:
                cons_counts['1'].append(_)
            else:
                cons_counts['-1'].append(_)

        # Maximum CONS wins
        out_dict['max_cons_wins_cnt'] = max(cons_counts['1'], key=lambda x: x[1])[1] if cons_counts['1'] else 0

        # Maximum CONS loss
        out_dict['max_cons_loss_cnt'] = max(cons_counts['-1'], key=lambda x: x[1])[1] if cons_counts['-1'] else 0

        # Maximal CONS profit
        out_dict['max_cons_wins_value'] = sum(max(cons_counts['1'], key=lambda x: x[1])[2]) if cons_counts['1'] else 0

        # Maximal CONS loss
        out_dict['max_cons_loss_value'] = sum(max(cons_counts['-1'], key=lambda x: x[1])[2]) if cons_counts['-1'] else 0

        # Average CONS wins
        out_dict['avg_cons_wins'] = sum([_[1] for _ in cons_counts['1']]) / len(cons_counts['1']) if cons_counts['1'] else 0

        # Average CONS loss
        out_dict['avg_cons_loss'] = sum([_[1] for _ in cons_counts['-1']]) / len(cons_counts['-1']) if cons_counts['-1'] else 0

        return {k: (round(v, 2) if type(v) != str else v) for k, v in out_dict.items()}

    except Exception as e:
        print(f"Exception in Generating MT Report : {e}")
        return None


def create_report(file_name, bt_config, trades_list, pnl_column="net_pnl"):
    """ Function to create an output report along with Input Config, Trades, MT Calculations """
    try:
        trades_df = pd.DataFrame(trades_list)
        input_df = pd.DataFrame(list(bt_config.items()), columns=["Key", "Value"])
        mt_dict = generate_mt_report(report_df=trades_df, pnl_column=pnl_column)
        mt_df = pd.DataFrame(list(mt_dict.items()), columns=["Key", "Value"])

        # Create an Excel file with multiple sheets
        with pd.ExcelWriter(file_name, engine='openpyxl') as writer:
            input_df.to_excel(writer, sheet_name='Config', index=False)
            trades_df.to_excel(writer, sheet_name='Trades', index=False)
            mt_df.to_excel(writer, sheet_name='Analysis', index=False)
    except Exception as e:
        print(f"Exception in Creating Report : {e}")
        pass


def round_strike_price(spot_price, multiple):
    """ Function to convert input price to nearest multiple """
    try:
        if multiple == 0:
            raise ValueError("Multiple must be greater than 0")
        return (spot_price // multiple) * multiple
    except Exception as e:
        print(f"Exception in Rounding to Multiple : {e}")
        return int(spot_price)


def get_bar_color(open_price, close_price):
    """Function to Check Bar Color"""
    try:
        if open_price <= close_price:
            return "green"
        else:
            return "red"
    except Exception as e:
        print(f"Exception in checking Bar Color : {e}")
        return None


def calculate_entry_quantity(investment, unit_price):
    """ Function to calculate Order Quantity to Purchase """
    try:
        return math.floor(investment / unit_price)
    except Exception as e:
        print(f"Exception in calculating order quantity : {e}")
        pass


def calculate_exit_quantity(total_quantity, target_split, sl_split):
    """ Function to generate accurate quantity for order processing """
    try:
        quantity_dict = {}

        if isinstance(total_quantity, int):
            t_quantity = [int(total_quantity * i) for i in list(target_split.values())]
            sl_quantity = [int(total_quantity) * i for i in list(sl_split.values())]

            t_diff = total_quantity - sum(t_quantity)
            if t_diff > 0:
                t_quantity[0] += t_diff

            for indx, key in enumerate(target_split.keys()):
                quantity_dict[key] = int(t_quantity[indx])

            sl_diff = total_quantity - sum(sl_quantity)
            if sl_diff > 0:
                sl_quantity[0] += sl_diff

            for indx, key in enumerate(sl_split.keys()):
                quantity_dict[key] = int(sl_quantity[indx])

        else:
            t_quantity = [total_quantity * i for i in list(target_split.values())]
            sl_quantity = [total_quantity * i for i in list(sl_split.values())]

            t_diff = total_quantity - sum(t_quantity)
            if t_diff > 0:
                t_quantity[0] += t_diff

            for indx, key in enumerate(target_split.keys()):
                quantity_dict[key] = float(t_quantity[indx])

            sl_diff = total_quantity - sum(sl_quantity)
            if sl_diff > 0:
                sl_quantity[0] += sl_diff

            for indx, key in enumerate(sl_split.keys()):
                quantity_dict[key] = float(sl_quantity[indx])

        return quantity_dict

    except Exception as e:
        print(f"Exception in Generate Exit Quantity : {e}")
        pass


def calculate_roi_percent(entry_price, current_price):
    """ Function to calculate ROI percentage """
    try:
        roi = round(float((current_price - entry_price) / entry_price) * 100, 2)
        print(f"ROI Percent: {roi}")
        return roi
    except Exception as e:
        print(f"Exception in Calculating ROI : {e}")
        pass


def calculate_liquidation_price(entry_price, leverage=10, position_type="LONG", mmr=0.005):
    """ Function to Calculate Liquidation Price"""
    try:
        if leverage <= 1:
            return None

        position_type = position_type.upper()

        if position_type == "LONG":
            denominator = leverage + 1 - (mmr * leverage)
            liquidation_price = (entry_price * leverage) / denominator
        elif position_type == "SHORT":
            denominator = leverage - 1 + (mmr * leverage)
            liquidation_price = (entry_price * leverage) / denominator
        else:
            raise ValueError("position_type must be 'LONG' or 'SHORT'")

        return round(liquidation_price, 2)
    except Exception as e:
        print(f"Exception in Calculating Liquidation Price : {e}")
        return None


# calculate_brokerage(buy_price=100, sell_price=110, quantity=1000, order_type="MARKET", position_type="LONG", market_type="options",
#                     no_of_orders=2, broker="zerodha", market="IN", lot_size=1, holding_type="intraday", exchange="NSE")
